cd /Users/huytruong/Workspace/Games/apks/

/Users/huytruong/Library/Android/sdk/build-tools/34.0.0/apksigner sign --ks tressette-release-key.jks --out output.apk Tressette.apk

adb install /Users/huytruong/Workspace/Games/apks/output.apk

huytruong8765

adb install /Users/huytruong/Workspace/Games/apks/Tressette.apk


cd /Users/huytruong/Workspace/Games/apks/web
python3 -m http.server 9100