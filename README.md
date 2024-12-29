
python -m grpc_tools.protoc -I. --python_out=. packet.proto
uvicorn main:app --reload
brew services start postgresql
