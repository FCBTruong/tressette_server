docker build -t my-game-server .

docker tag my-game-server:latest 412381763978.dkr.ecr.ap-southeast-1.amazonaws.com/containers/tressette:latest

docker push 412381763978.dkr.ecr.ap-southeast-1.amazonaws.com/containers/tressette:latest
