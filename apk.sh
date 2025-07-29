cd /Users/huytruong/Workspace/Games/apks/

/Users/huytruong/Library/Android/sdk/build-tools/34.0.0/apksigner sign --ks tressette-release-key.jks --out output.apk Tressette.apk

adb install /Users/huytruong/Workspace/Games/apks/output.apk

huytruong8765

adb install /Users/huytruong/Workspace/Games/apks/Tressette.apk


cd /Users/huytruong/Workspace/Games/apks/web
python3 -m http.server 9100



# COPY secrets if lost
aws ecr get-login-password --region ap-southeast-1 \
| docker login --username AWS --password-stdin 412381763978.dkr.ecr.ap-southeast-1.amazonaws.com

# Step 1: Create container (doesn't start it)
cid=$(docker create 412381763978.dkr.ecr.ap-southeast-1.amazonaws.com/containers/tressette:latest)

docker cp "$cid":/app/src/config/.env .env

docker rm "$cid"
