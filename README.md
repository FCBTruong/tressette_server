
python -m grpc_tools.protoc -I. --python_out=. src/base/network/packets/packet.proto
uvicorn main:app --reload
brew services start postgresql
brew services start redis

chmod +x /Users/huytruong/Workspace/Games/tressette_server/build.sh
