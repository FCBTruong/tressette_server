
python -m grpc_tools.protoc -I. --python_out=. message.proto
uvicorn main:app --reload