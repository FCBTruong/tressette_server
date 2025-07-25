Hi Recruiter,

This is one of my key projects — a real-time online multiplayer game I built to showcase my backend development skills.

The backend is written in **Python** using **FastAPI**, and communicates via **WebSocket** using **Protobuf** for efficient data transfer.  
It includes login via Firebase, full multiplayer logic, and supports integrated payments (Apple, Google, PayPal).  
The system runs on **AWS ECS**, uses **PostgreSQL** for storage, **Redis** for caching, and **Amazon S3** for hosting static assets and CDN.

I’ve also implemented async architecture using Python’s `async/await` to handle concurrent connections smoothly.


You can play the game at: [https://tressette.clareentertainment.com/](https://tressette.clareentertainment.com/)
or download it from Google Play and the App Store (search **Tressette Royal Online**).

Here are some screenshots:
![Screenshot 1](assets/game_screen1.png)
![Screenshot 2](assets/game_screen2.png)



Below is the architecture diagram for the project:
### 1. Overview
![Tressette Architecture](assets/overview_architecture.png)
---
### 2. Flow build
![Deploy AWS](assets/flow-build.png)
---
### 3. Flow sequence

#### 1. Signup/login Firebase
![Flow Signup Firebases](assets/flow-register-account.png)

#### 2. Login
![Sample Flow Login](assets/flow-login.drawio.png)

#### 3. Play Card (In game)
![Play Card Flow](assets/flow-play-action.drawio.png)

#### 4. Payment
![Payment Flow](assets/flow-pay.drawio.png)

---

## 🚀 Setup Instructions

### 1. Set up Python environment
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
````

### 2. Start local services (macOS)

```bash
brew services start postgresql
brew services start redis
```

### 3. Generate gRPC code

```bash
python -m grpc_tools.protoc -I. --python_out=. src/base/network/packets/packet.proto
```

### 4. Run the server

```bash
uvicorn main:app --reload
```

---

Thanks for reviewing!


