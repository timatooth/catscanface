set -e
mkdir -p build

# thanks @aeddi: https://github.com/aeddi/aws-lambda-python-opencv
if [ ! -f /tmp/aws-lambda-python-opencv-prebuilt.zip ]; then
	echo "Downloading prebuilt aeddi/aws-lambda-python-opencv..."
	curl -L https://github.com/aeddi/aws-lambda-python-opencv/releases/download/Prebuilt/aws-lambda-python-opencv-prebuilt.zip > /tmp/aws-lambda-python-opencv-prebuilt.zip
	unzip -d build /tmp/aws-lambda-python-opencv-prebuilt.zip
	mv build/aws-lambda-python-opencv-prebuilt/* build/
	rmdir build/aws-lambda-python-opencv-prebuilt
fi
cp catscan.py build/
cp *.xml build/
cd build
zip -r /tmp/catfacescan-dist.zip *
echo "Uploading lambda..."
# Preparing and deploying Function to Lambda
aws lambda update-function-code --function-name catscanface --zip-file "fileb:///tmp/catfacescan-dist.zip"
echo "Done"
