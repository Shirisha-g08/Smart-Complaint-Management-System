# Smart Complaint Management System

A cloud-based complaint management web application built with **Flask**, **AWS DynamoDB**, and **AWS SNS**. Designed to run on **AWS EC2**.

---

## Architecture

```
Browser  →  Flask App (EC2)  →  DynamoDB (storage)
                          ↓
                    SNS (email/SMS notifications)
                          ↑
                    IAM (access control)
```

---

## Features

| Role  | Capabilities |
|-------|-------------|
| User  | Register, login, submit complaints, view own complaint status |
| Admin | View all complaints, update status, add remarks, trigger SNS notifications |

- Status flow: **Pending → In Progress → Resolved**
- SNS notification sent on submit and every status update
- Password hashing with Werkzeug (bcrypt)
- Session-based authentication (Flask sessions)

---

## Project Structure

```
project-siri/
├── app.py                        # Flask application
├── requirements.txt
├── .env.example                  # Environment variable template
├── aws/
│   └── setup_aws.py              # One-time AWS resource provisioner
├── templates/
│   ├── base.html
│   ├── index.html                # Landing page
│   ├── login.html / register.html
│   ├── dashboard.html            # User dashboard
│   ├── submit_complaint.html
│   ├── complaint_detail.html
│   ├── admin_login.html
│   ├── admin_dashboard.html
│   ├── admin_complaint.html      # Admin review + update
│   ├── 404.html / 500.html
└── static/
    ├── css/style.css
    └── js/main.js
```

---

## Local Setup

### 1. Clone & create virtual environment

```bash
git clone <repo-url>
cd Smart-Complaint-Management-System
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your AWS credentials and settings
```

Key variables in `.env`:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session secret (change to a long random string) |
| `AWS_REGION` | e.g. `us-east-1` |
| `AWS_ACCESS_KEY_ID` | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| `DYNAMODB_USERS_TABLE` | Default: `scms_users` |
| `DYNAMODB_COMPLAINTS_TABLE` | Default: `scms_complaints` |
| `SNS_TOPIC_ARN` | Output of `setup_aws.py` |
| `ADMIN_EMAIL` | Admin login email |
| `ADMIN_PASSWORD` | Admin login password |

### 4. Provision AWS resources (run once)

```bash
python aws/setup_aws.py
```

This creates:
- DynamoDB table `scms_users` (PK: `email`)
- DynamoDB table `scms_complaints` (PK: `complaint_id`, GSI: `user_email-index`)
- SNS topic `scms-notifications`

Copy the printed `SNS_TOPIC_ARN` into your `.env` file.

### 5. Subscribe to SNS notifications

Go to **AWS Console → SNS → Topics → scms-notifications → Create subscription**  
- Protocol: `Email`  
- Endpoint: your email address  
- Confirm the subscription via the email AWS sends

### 6. Run the app

```bash
python app.py
```

Visit `http://localhost:5000`

---

## AWS EC2 Deployment

### 1. Launch EC2 Instance

- AMI: Amazon Linux 2023 (or Ubuntu 22.04)
- Instance type: `t2.micro` (free tier)
- Security Group inbound rules:
  - Port 22 (SSH)
  - Port 80 (HTTP)
  - Port 5000 (Flask dev) — or use nginx reverse proxy

### 2. Assign IAM Role to EC2

Create an IAM role with these policies and attach it to the EC2 instance  
(this avoids hard-coding credentials):

```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:Scan",
    "dynamodb:Query"
  ],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/scms_users",
    "arn:aws:dynamodb:*:*:table/scms_complaints",
    "arn:aws:dynamodb:*:*:table/scms_complaints/index/*"
  ]
},
{
  "Effect": "Allow",
  "Action": "sns:Publish",
  "Resource": "arn:aws:sns:*:*:scms-notifications"
}
```

### 3. Install dependencies on EC2

```bash
sudo yum update -y                      # Amazon Linux
sudo yum install python3 python3-pip git -y

git clone <repo-url>
cd Smart-Complaint-Management-System
pip3 install -r requirements.txt
```

### 4. Run the app

```bash
python3 app.py
```

### 5. (Optional) Nginx reverse proxy

```nginx
server {
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## DynamoDB Schema

### `scms_users`

| Attribute | Type | Key |
|---|---|---|
| `email` | String | Partition Key |
| `user_id` | String | |
| `name` | String | |
| `phone` | String | |
| `password_hash` | String | |
| `created_at` | String | |

### `scms_complaints`

| Attribute | Type | Key |
|---|---|---|
| `complaint_id` | String | Partition Key |
| `user_email` | String | GSI Partition Key |
| `timestamp` | String | GSI Sort Key |
| `user_name` | String | |
| `title` | String | |
| `description` | String | |
| `category` | String | |
| `status` | String | Pending / In Progress / Resolved |
| `remarks` | String | |
| `updated_at` | String | |

**GSI:** `user_email-index` — enables efficient per-user complaint queries.

---

## URL Routes

| Method | URL | Description |
|---|---|---|
| GET | `/` | Landing page |
| GET/POST | `/register` | User registration |
| GET/POST | `/login` | User login |
| GET | `/logout` | User logout |
| GET | `/dashboard` | User complaint dashboard |
| GET/POST | `/submit` | Submit new complaint |
| GET | `/complaint/<id>` | View complaint detail |
| GET/POST | `/admin/login` | Admin login |
| GET | `/admin/logout` | Admin logout |
| GET | `/admin/dashboard` | Admin complaint list |
| GET/POST | `/admin/complaint/<id>` | Review and update complaint |

---