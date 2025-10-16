Step 1: Generate the Stub Files
Prerequisites

Python 3.10 or later. Install Python from https://www.python.org/downloads/.
Install the Python package manager by running this command in the terminal.

pip3 install grpcio grpcio-tools avro requests
You can use a different package manager.

Clone the GitHub repository for Pub/Sub API from https://github.com/forcedotcom/pub-sub-api. The proto file name is pubsub_api.proto.

Switch to the python directory.

cd python
Generate the stubs for the Pub/Sub API by running this command from the cloned directory.

python3 -m grpc_tools.protoc --proto_path=../ pubsub_api.proto --python_out=. --grpc_python_out=.
This command generates two files in your current directory: pubsub_api_pb2.py and pubsub_api_pb2_grpc.py. It also generates client and server code and protocol buffer code for populating, serializing, and retrieving message types.
