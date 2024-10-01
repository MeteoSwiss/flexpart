#!/usr/bin/python3
import boto3  # pip install boto3
import os
import argparse
from datetime import datetime

# current date and time
now = datetime.now()

parser = argparse.ArgumentParser()
parser.add_argument(
    "--directory", help="directory to upload to s3", type=str)
parser.add_argument(
    "--bucket", help="S3 bucket'name to upload to", type=str, default=os.getenv('FLEXPART_S3_BUCKETS__OUTPUT__NAME'))
parser.add_argument(
    "--endpoint_url", help="S3 bucket's URL to upload to", type=str, default=os.getenv('FLEXPART_S3_BUCKETS__OUTPUT__ENDPOINT_URL'))
args = parser.parse_args()

if "http_proxy" in os.environ:
    del os.environ['http_proxy']
if "https_proxy" in os.environ:
    del os.environ['https_proxy']
if "HTTP_PROXY" in os.environ:
    del os.environ['HTTP_PROXY']
if "HTTPS_PROXY" in os.environ:
    del os.environ['HTTPS_PROXY']

def uploadDirectory(root_path, bucket_name, endpoint_url):

    print(f"Uploading directory: {root_path} to bucket: {bucket_name} in endpoint_url: {endpoint_url}")

    try:
        s3_resource = boto3.resource(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('S3_SECRET_KEY')
        )
        my_bucket = s3_resource.Bucket(bucket_name)
        top_dir = os.path.join(now.strftime("%m%d%Y%H:%M:%S"),os.path.basename(os.path.dirname(root_path)))
        if os.path.exists(root_path):
            for path, subdirs, files in os.walk(root_path):
                path = path.replace("\\","/")
                if path == root_path:
                    directory_name = top_dir
                else:
                    directory_name = os.path.join(top_dir,path.replace(root_path,""))
                for file in files:
                    my_bucket.upload_file(os.path.join(path, file), directory_name+'/'+file)
        else:
            raise Exception("Directory provided to upload does not exist.")
    except Exception as err:
        print(err)

if args.bucket is None:
    print("Skipping upload to S3 as S3_BUCKET_NAME environment variable is unset.")
else:
    uploadDirectory(args.directory, args.bucket, args.endpoint_url)
