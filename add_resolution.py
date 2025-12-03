"""This script reads a csv file and adds each bscan resolution to the dataframe"""

import pandas as pd
import argparse
from multiprocessing import Pool
from tqdm import tqdm
from PIL import Image

def get_resolution(row):
    """Get the resolution of the bscan"""
    # read the image
    width, height = Image.open(row['file_path_coris']).size
    
    # read Start_X and End_X
    start_x = row.get('Start_X', 0)
    end_x = row.get('End_X', 0)
    
    # calculate the resolution
    row['resolution'] = (end_x - start_x) / width
    row['height'] = height
    row['width'] = width
    
    return row    

def main(args):
    """Main function"""
    df = pd.read_csv(args.input_file)
    df = df[df['file_path_coris'].notna()]

    new_data = []
    with Pool(30) as pool:
        for info in tqdm(pool.imap_unordered(get_resolution, df.to_dict(orient='records')), total=len(df)):
            new_data.append(info)

    df = pd.DataFrame(new_data)
    df.to_csv(args.output_file, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    args = parser.parse_args()
    main(args)