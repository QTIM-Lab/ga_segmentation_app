from flask import Flask, render_template, send_from_directory, jsonify, request, redirect, url_for, send_file
import os
import pandas as pd
from PIL import Image
from io import BytesIO
import argparse
from collections import defaultdict
import csv
# from werkzeug.middleware.dispatcher import DispatcherMiddleware # DELETE ME

app = Flask(__name__)

BASE_PATH = os.environ.get('BASE_PATH', '')  # Set to /ga_segmentation_app in production

# Global variable to store image paths
IMAGE_PATHS = {}
VOLUME_PATHS = {}
RESOLUTIONS = {}

def load_image_paths(file_path, volume_column='volume', path_column='path'):
    """Load image paths from a CSV file."""
    global IMAGE_PATHS
    global VOLUME_PATHS
    global RESOLUTIONS
    try:
        data = pd.read_csv(file_path)
        data = data[data.ImageNumber > 0]
        data['resolution'] = data['resolution'] * 1000 # convert to um/pixel
        IMAGE_PATHS = data.groupby(volume_column).apply(lambda x: x.sort_values('ImageNumber')[path_column].tolist()).to_dict()
        VOLUME_PATHS = data.groupby(volume_column)[path_column].apply(lambda x: os.path.dirname(x.iloc[0])).to_dict()
        RESOLUTIONS = data.groupby(volume_column).apply(lambda x: x.sort_values('ImageNumber')[['resolution', path_column]].set_index(path_column).to_dict()).to_dict()
        print(f"Loaded {len(IMAGE_PATHS)} image paths from {file_path} (volume: {volume_column}, path: {path_column})")
    except FileNotFoundError:
        print(f"Warning: Image paths file {file_path} not found. Using default paths.")
        IMAGE_PATHS = {}
        VOLUME_PATHS = {}
        RESOLUTIONS = {}
    except Exception as e:
        print(f"Error parsing CSV file {file_path}: {e}")
        IMAGE_PATHS = {}

def get_image_path(volume, filename):
    """Get the full path to an image file."""
    # Use the specific folder for this volume if available
    if volume in VOLUME_PATHS:
        return os.path.join(VOLUME_PATHS[volume], filename)
    
    # If no specific path found, return None to indicate volume not found
    return None

def get_volume(volume):
    """Get the directory path for a volume."""
    # Use the specific folder for this volume if available
    if volume in IMAGE_PATHS:
        return IMAGE_PATHS[volume]
    
    # If no specific path found, return None to indicate volume not found
    return []

@app.route('/')
def root():
    return redirect(BASE_PATH + '/volumes')

@app.route('/index')
def index():
    return render_template('index.html', BASE_PATH = BASE_PATH)

@app.route('/index_v2')
def index_v2():
    return render_template('index_v2.html')


@app.route('/image')
def serve_image():
    volume = request.args.get('volume')
    filename = request.args.get('filename')
    if not volume or not filename:
        return 'Missing volume or filename', 400
    
    file_path = get_image_path(volume, filename)
    # print(f"Serving image {filename} from volume {volume} at {file_path}")
    if file_path is None:
        return 'Volume not found in image paths', 404
    if not os.path.exists(file_path):
        return 'Image not found', 404
    
    # Check if it's a J2K file and convert to PNG on the fly
    if filename.lower().endswith('.j2k') or filename.lower().endswith('.jp2'):
        try:
            with Image.open(file_path) as im:
                rgb_im = im.convert('RGB')
                buf = BytesIO()
                rgb_im.save(buf, format='JPEG')
                buf.seek(0)
                # print(f"Converted {filename} to JPEG")
                return send_file(buf, mimetype='image/jpeg')
        except Exception as e:
            return f'Failed to convert image: {str(e)}', 500
    else:
        print(f"Sending {filename} from {file_path}")
        # Send file from the directory containing the file
        directory = os.path.dirname(file_path)
        return send_from_directory(directory, filename)

@app.route('/images_in_volume')
def images_in_volume():
    volume = request.args.get('volume')
    if not volume:
        return jsonify([])
    
    image_files = get_volume(volume)
    return jsonify(image_files)

@app.route('/image_resolution')
def get_image_resolution():
    volume = request.args.get('volume')
    filename = request.args.get('filename')
    print(f"Getting resolution for volume: {volume}, filename: {filename}")
    
    if not volume or not filename:
        print("Missing volume or filename")
        return jsonify({'resolution': 1.0})  # Default resolution if not found
    
    # Get the resolution for this specific image
    if volume in RESOLUTIONS:
        volume_resolutions = RESOLUTIONS[volume]
        # print(volume_resolutions)
        if volume in IMAGE_PATHS:
            resolution = volume_resolutions['resolution'][filename]
            print(f"Found resolution: {resolution}")
            return jsonify({'resolution': float(resolution)})
        else:
            print(f"Image {filename} not found in IMAGE_PATHS")
    else:
        print(f"Volume [{volume}] not found in RESOLUTIONS")
    
    print("Returning default resolution 1.0")
    return jsonify({'resolution': 1.0})  # Default resolution if not found

@app.route('/save_lines', methods=['POST'])
def save_lines():
    data = request.get_json()
    if not data or 'lines' not in data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
    lines = data['lines']
    volume = data.get('volume', None)
    output_dir = os.path.join(app.root_path, 'output')
    os.makedirs(output_dir, exist_ok=True)
    if volume:
        output_path = os.path.join(output_dir, f'{volume}_lines.csv')
    else:
        output_path = os.path.join(output_dir, 'lines.csv')
    
    # Save in new format with multiple lines per image
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['volume_id', 'index', 'filepath', 'line_index', 'x', 'color'])
        for image_data in lines:
            filepath = image_data['filepath']
            image_lines = image_data.get('lines', [])
            
            for line_index, line in enumerate(image_lines):
                display_x = line.get('x', 0)
                
                writer.writerow([
                    volume,  # volume_id
                    image_data['index'], 
                    filepath, 
                    line_index,
                    display_x,  # Keep original display coordinates for reference
                    line.get('color', 'red')
                ])
    
    return jsonify({'status': 'success', 'message': 'Lines saved'})

@app.route('/volumes')
def list_volumes():
    output_dir = os.path.join(app.root_path, 'output')
    
    # Only use volumes from IMAGE_PATHS
    if not IMAGE_PATHS:
        return render_template('volumes.html', volumes=[])
    
    volumes = list(IMAGE_PATHS.keys())
    volumes.sort()
    
    volume_infos = []
    for volume in volumes:
        annotation_file = os.path.join(output_dir, f'{volume}_lines.csv')
        has_annotation = os.path.isfile(annotation_file)
        
        # Count files in the volume
        img_list = get_volume(volume)
        
        volume_infos.append({
            'name': volume, 
            'has_annotation': has_annotation,
            'file_count': len(img_list)
        })
    
    return render_template('volumes.html', volumes=volume_infos, BASE_PATH = BASE_PATH)

@app.route('/next_volume')
def get_next_volume():
    """Get the next volume in the sorted list."""
    current_volume = request.args.get('volume')
    if not current_volume:
        return jsonify({'error': 'No current volume provided'}), 400
    
    if not IMAGE_PATHS:
        return jsonify({'error': 'No volumes available'}), 400
    
    volumes = sorted(list(IMAGE_PATHS.keys()))
    try:
        current_index = volumes.index(current_volume)
        if current_index < len(volumes) - 1:
            next_volume = volumes[current_index + 1]
            return jsonify({'next_volume': next_volume, 'is_last': False})
        else:
            return jsonify({'next_volume': None, 'is_last': True})
    except ValueError:
        return jsonify({'error': 'Current volume not found'}), 400

@app.route('/previous_volume')
def get_previous_volume():
    """Get the previous volume in the sorted list."""
    current_volume = request.args.get('volume')
    if not current_volume:
        return jsonify({'error': 'No current volume provided'}), 400
    
    if not IMAGE_PATHS:
        return jsonify({'error': 'No volumes available'}), 400
    
    volumes = sorted(list(IMAGE_PATHS.keys()))
    try:
        current_index = volumes.index(current_volume)
        if current_index > 0:
            previous_volume = volumes[current_index - 1]
            return jsonify({'previous_volume': previous_volume, 'is_first': False})
        else:
            return jsonify({'previous_volume': None, 'is_first': True})
    except ValueError:
        return jsonify({'error': 'Current volume not found'}), 400

@app.route('/annotations')
def get_annotations():
    volume = request.args.get('volume')
    if not volume:
        return jsonify([])
    output_dir = os.path.join(app.root_path, 'output')
    annotation_file = os.path.join(output_dir, f'{volume}_lines.csv')
    if not os.path.isfile(annotation_file):
        return jsonify([])
    import csv
    annotations = []
    
    # Group lines by filepath
    file_lines = {}
    
    with open(annotation_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filepath = row['filepath']
            if filepath not in file_lines:
                file_lines[filepath] = []
            
            # Check format based on available columns
            if 'x' in row and 'line_index' not in row:
                # Old format - single x coordinate
                file_lines[filepath].append({
                    'x': float(row['x']),  # Keep x for vertical lines
                    'color': 'red',
                    'id': f"old_{row['index']}"
                })
            elif 'volume_id' in row:
                # New format with volume_id - use saved color if available, otherwise assign based on line_index
                line_index = int(row['line_index'])
                if 'color' in row:
                    # Use the saved color
                    color = row['color']
                else:
                    # Fallback: assign colors based on line_index to maintain progression
                    color_index = line_index // 2  # Each pair gets the same color
                    colors = ['red', 'blue', 'green', 'orange', 'purple', 'cyan', 'magenta', 'yellow']
                    color = colors[color_index % len(colors)]
                
                # Use display coordinates for frontend display (backward compatibility)
                display_x = float(row['x'])
                file_lines[filepath].append({
                    'x': display_x,
                    'color': color,
                    'id': f"line_{row['line_index']}"
                })
            else:
                # Intermediate format with color/line_id
                file_lines[filepath].append({
                    'x': float(row['x']),
                    'color': row.get('color', 'red'),
                    'id': row.get('line_id', f"line_{row['line_index']}")
                })
    
    # Convert to the format expected by frontend
    for filepath, lines in file_lines.items():
        annotations.append({
            'filepath': filepath,
            'lines': lines
        })
    
    return jsonify(annotations)

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    parser = argparse.ArgumentParser(description='Run the GA Segmentation App.')
    parser.add_argument('--host', default='0.0.0.0', help='Host address to bind to.')
    # parser.add_argument('--prefix', default='', help='URL prefix for reverse proxy (e.g., /ga_segmentation_app)') # DELETE ME
    parser.add_argument('--port', type=int, default=5005, help='Port to listen on.')
    parser.add_argument('--image-paths', help='CSV file containing image paths mapping.')
    parser.add_argument('--volume-column', default='id', help='Name of the volume column in the CSV file (default: id).')
    parser.add_argument('--path-column', default='file_path_coris', help='Name of the path column in the CSV file (default: file_path_coris).')
    args = parser.parse_args()
    
    # Load image paths if provided
    if args.image_paths:
        load_image_paths(args.image_paths, args.volume_column, args.path_column)
    
    # DELETE ME
    # if args.prefix:
    #     print(args.prefix)
    #     app.wsgi_app = DispatcherMiddleware(Flask('dummy'), {
    #         args.prefix: app.wsgi_app
    #     })
    
    app.run(debug=debug_mode, host=args.host, port=args.port)