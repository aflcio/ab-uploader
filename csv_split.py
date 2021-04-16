import math
import pandas as pd
import s3fs
import csv

def split_and_convert(file_name, src_dir, dest_dir, rows=200):
    df = pd.read_csv(f'{src_dir}/{file_name}.txt', sep="\t")
    chunks = math.ceil(len(df) / rows)
    # Initial values
    lo = 0
    hi = rows
    # Loop through chunks
    for i in range(chunks):
        dest = f'{dest_dir}/{file_name}-{i+1:03}.csv'
        if hi > len(df):
            hi = len(df)
        df[lo:hi].to_csv(dest, index=False)
        lo = hi
        hi += rows

def to_csv(txt_file):
    csv_file = txt_file[:-3] + 'csv'
    with open(txt_file, "r") as in_text, open(csv_file, "w") as out_csv:
        in_reader = csv.reader(in_text, delimiter='\t')
        out_writer = csv.writer(out_csv)
        for row in in_reader:
            out_writer.writerow(row)
