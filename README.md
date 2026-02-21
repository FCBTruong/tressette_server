Dear Hiring Manager,

This project implements an online turn-based card game based on a client–server architecture.
The server operates as an authoritative source of truth, handling all game logic, validating player actions, and synchronizing game state across clients.

## Features

* **Core Gameplay Logic**
  Implements the full turn-based card game mechanics, including turn handling, rule validation, match flow, and win conditions.

* **Authoritative Server Architecture**
  Server-side validation of all player actions to ensure fairness, consistency, and cheat prevention.

* **User Management**
  Player registration, authentication, profile management, and account data handling.

* **Inventory System**
  Manage owned cards, items, rewards, and player assets.

* **In-Game Shop**
  Purchase cards, packs, or items using in-game currency.

* **Friends & Social System**
  Add friends, manage friend lists, and enable social interactions between players.

* **Client–Server Networking**
  Real-time communication between client and server with synchronized game state management.

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

## Dashboard
![Overview](assets/metrics-overview.png)

---

Thanks for reviewing!


