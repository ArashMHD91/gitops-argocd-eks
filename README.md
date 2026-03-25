# GitOps-Based App Deployment with ArgoCD on EKS

![AWS](https://img.shields.io/badge/AWS-EKS%20%7C%20ECR%20%7C%20IAM-orange?logo=amazonaws)
![Terraform](https://img.shields.io/badge/Terraform-IaC-purple?logo=terraform)
![ArgoCD](https://img.shields.io/badge/ArgoCD-GitOps-blue?logo=argo)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-CI%2FCD-black?logo=githubactions)
![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-red?logo=prometheus)
![Grafana](https://img.shields.io/badge/Grafana-Dashboards-orange?logo=grafana)

A hands-on project that walks you through building a **production-grade GitOps pipeline** from scratch. You will provision an EKS cluster with Terraform, containerize a Flask app, automate builds with GitHub Actions, deploy with ArgoCD, and monitor everything with Prometheus and Grafana.

---

## What You Will Build

```
You push code
      │
      ▼
GitHub Actions (CI)
  → builds Docker image
  → tags with commit SHA
  → pushes to Amazon ECR
  → updates k8s manifest
      │
      ▼
ArgoCD (CD) watches your repo
  → detects manifest change
  → auto-deploys to EKS
      │
      ▼
Flask app running on EKS
  → exposed via AWS LoadBalancer
  → monitored by Prometheus + Grafana
```

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| Terraform | Provision AWS infrastructure (VPC, EKS, ECR, IAM) |
| Amazon EKS | Managed Kubernetes cluster |
| Amazon ECR | Private Docker image registry |
| GitHub Actions | CI pipeline — build and push on every commit |
| ArgoCD | GitOps CD — auto-deploy on manifest change |
| Flask | Simple Python web application |
| Prometheus | Metrics collection |
| Grafana | Metrics visualization and dashboards |
| Helm | Package manager for Kubernetes |

---

## Project Structure

```
gitops-argocd-eks/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI pipeline
├── app/
│   ├── app.py                  # Flask application
│   ├── requirements.txt        # Python dependencies
│   └── Dockerfile              # Container build instructions
├── k8s-manifests/
│   ├── deployment.yaml         # Kubernetes Deployment (2 replicas)
│   ├── service.yaml            # LoadBalancer Service
│   └── .argocd/
│       └── application.yaml    # ArgoCD Application definition
├── terraform/
│   ├── main.tf                 # VPC, EKS, ECR, IAM resources
│   ├── variables.tf            # Input variables
│   ├── outputs.tf              # Output values
│   └── versions.tf             # Provider version constraints
└── monitoring/                 # Prometheus & Grafana configs
```

---

## Prerequisites

Make sure you have these installed before starting:

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.3.0
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/) >= 3.x
- [Docker](https://docs.docker.com/get-docker/)
- An AWS account with programmatic access

---

## Part 1 — Infrastructure with Terraform

### What we build
- A **VPC** with 2 public subnets across availability zones
- An **EKS Cluster** — managed Kubernetes control plane (v1.29)
- An **EKS Node Group** — 2x `t3.small` worker nodes (auto-scaling: 1–3)
- An **ECR Repository** — private Docker registry with image scanning
- **IAM Roles** — least-privilege roles for EKS cluster and nodes

### Step 1: Configure AWS CLI

```bash
aws configure
# Enter: Access Key ID, Secret Access Key, region (eu-central-1), output format (json)
```

Verify connection:

```bash
aws sts get-caller-identity
```

### Step 2: Create project structure

```bash
mkdir -p gitops-argocd-eks/{terraform,app,k8s-manifests/.argocd,monitoring}
cd gitops-argocd-eks
touch README.md
```

### Step 3: Create Terraform files

```bash
cd terraform
```

**`versions.tf`** — locks provider versions so the code is reproducible by anyone:

```hcl
terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
```

**`variables.tf`** — all configurable values in one place:

```hcl
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "eu-central-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "gitops-cluster"
}

variable "cluster_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.29"
}

variable "node_instance_type" {
  description = "EC2 instance type for worker nodes"
  type        = string
  default     = "t3.small"
}

variable "node_desired_size" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 2
}

variable "app_name" {
  description = "Application name used for ECR and tagging"
  type        = string
  default     = "gitops-app"
}
```

**`main.tf`** — all AWS resources:

```hcl
data "aws_availability_zones" "available" {}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "${var.cluster_name}-vpc" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                        = "${var.cluster_name}-public-${count.index}"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.cluster_name}-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${var.cluster_name}-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_iam_role" "eks_cluster" {
  name = "${var.cluster_name}-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role" "eks_nodes" {
  name = "${var.cluster_name}-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "ecr_read_only" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids = aws_subnet.public[*].id
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
  tags       = { Name = var.cluster_name }
}

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.public[*].id
  instance_types  = [var.node_instance_type]

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = 1
    max_size     = 3
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.ecr_read_only,
  ]

  tags = { Name = "${var.cluster_name}-nodes" }
}

resource "aws_ecr_repository" "app" {
  name                 = var.app_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = var.app_name }
}
```

**`outputs.tf`** — prints values you will need in later steps:

```hcl
output "cluster_name" {
  value = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "aws_region" {
  value = var.aws_region
}
```

### Step 4: Deploy the infrastructure

```bash
terraform init
terraform fmt
terraform validate
terraform plan
terraform apply
```

> EKS cluster creation takes 10–15 minutes. Node group provisioning takes another 5–10 minutes. This is normal.

### Step 5: Connect kubectl to your cluster

```bash
aws eks update-kubeconfig --region eu-central-1 --name gitops-cluster
```

Verify nodes are ready:

```bash
kubectl get nodes
```

Expected — both nodes show `Ready`:

```
NAME                                          STATUS   ROLES    AGE   VERSION
ip-10-0-0-xx.eu-central-1.compute.internal    Ready    <none>   5m    v1.29.x
ip-10-0-1-xx.eu-central-1.compute.internal    Ready    <none>   5m    v1.29.x
```

---

## Part 2 — Flask Application + Docker

### What we build
A Python Flask app with three endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Returns app info and version |
| `GET /health` | Health check — used by Kubernetes liveness and readiness probes |
| `GET /metrics` | Prometheus metrics — scraped automatically |

### Step 1: Create app files

```bash
cd ../app
```

**`requirements.txt`:**

```
flask==3.0.0
prometheus-flask-exporter==0.23.1
```

**`app.py`:**

```python
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
metrics = PrometheusMetrics(app)

@app.route("/")
def home():
    return jsonify({
        "app": "gitops-app",
        "version": "1.0.0",
        "status": "running",
        "message": "GitOps with ArgoCD on EKS"
    })

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

**`Dockerfile`:**

```dockerfile
# Slim base image — smaller size, less attack surface
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first to leverage Docker layer caching
# Only reinstalls packages when requirements.txt actually changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5000
CMD ["python", "app.py"]
```

### Step 2: Build and push to ECR

```bash
# Authenticate Docker to ECR
aws ecr get-login-password --region eu-central-1 | \
  docker login --username AWS --password-stdin <YOUR_ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com

# Build
docker build -t gitops-app .

# Tag with your ECR URL
docker tag gitops-app:latest <YOUR_ECR_URL>:latest

# Push
docker push <YOUR_ECR_URL>:latest

# Verify
aws ecr list-images --repository-name gitops-app --region eu-central-1
```

Replace `<YOUR_ECR_URL>` with the `ecr_repository_url` value from `terraform output`.

---

## Part 3 — CI Pipeline with GitHub Actions

### What the pipeline does
Every time you push a change to `app/`, GitHub Actions will automatically:
1. Build a new Docker image
2. Tag it with the exact Git commit SHA
3. Push it to ECR
4. Update `k8s-manifests/deployment.yaml` with the new image tag
5. Commit and push the manifest change — ArgoCD picks this up automatically

### Step 1: Initialize Git and push to GitHub

```bash
cd ..  # project root
git init
git branch -M main

cat > .gitignore << 'EOF'
terraform/.terraform/
terraform/.terraform.lock.hcl
terraform/terraform.tfstate
terraform/terraform.tfstate.backup
terraform/*.tfvars
__pycache__/
*.pyc
.env
.DS_Store
EOF

git add .
git commit -m "initial commit: terraform infrastructure and flask app"
git remote add origin https://github.com/<YOUR_USERNAME>/gitops-argocd-eks.git
git push -u origin main
```

### Step 2: Add GitHub Secrets

Go to your repo on GitHub → **Settings → Secrets and variables → Actions → New repository secret**

Add these 4 secrets:

| Secret Name | Value |
|-------------|-------|
| `AWS_ACCESS_KEY_ID` | Your AWS Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | Your AWS Secret Access Key |
| `AWS_REGION` | `eu-central-1` |
| `ECR_REPOSITORY_URL` | Your full ECR URL from Terraform output |

### Step 3: Create the workflow file

```bash
mkdir -p .github/workflows
```

**`.github/workflows/ci.yml`:**

```yaml
name: CI - Build and Push to ECR

on:
  push:
    branches:
      - main
    paths:
      - 'app/**'   # only triggers when app/ files change

env:
  AWS_REGION: ${{ secrets.AWS_REGION }}
  ECR_REPOSITORY_URL: ${{ secrets.ECR_REPOSITORY_URL }}

jobs:
  build-and-push:
    name: Build and Push Docker Image
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build, tag and push image to ECR
        env:
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REPOSITORY_URL:$IMAGE_TAG -t $ECR_REPOSITORY_URL:latest ./app
          docker push $ECR_REPOSITORY_URL:$IMAGE_TAG
          docker push $ECR_REPOSITORY_URL:latest
          echo "Built and pushed: $ECR_REPOSITORY_URL:$IMAGE_TAG"

      - name: Update Kubernetes manifest with new image tag
        env:
          IMAGE_TAG: ${{ github.sha }}
        run: |
          if [ -f k8s-manifests/deployment.yaml ]; then
            sed -i "s|image: .*gitops-app.*|image: $ECR_REPOSITORY_URL:$IMAGE_TAG|g" k8s-manifests/deployment.yaml
            git config user.name "github-actions"
            git config user.email "github-actions@github.com"
            git add k8s-manifests/deployment.yaml
            git diff --staged --quiet || git commit -m "ci: update image tag to $IMAGE_TAG"
            git push
          else
            echo "deployment.yaml not found yet, skipping manifest update"
          fi
```

Push the workflow:

```bash
git add .github/
git commit -m "ci: add GitHub Actions workflow"
git push
```

Trigger it by making a change to `app/app.py` and pushing.

---

## Part 4 — Install ArgoCD on EKS

### Step 1: Create namespace and install

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### Step 2: Wait for all pods to be running

```bash
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
kubectl get pods -n argocd
```

All 7 pods should show `Running`.

### Step 3: Expose the ArgoCD UI

```bash
kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "LoadBalancer"}}'
kubectl get svc argocd-server -n argocd
```

Copy the `EXTERNAL-IP` value — this is your ArgoCD dashboard URL.

### Step 4: Get the admin password

```bash
kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" | base64 --decode
```

Open `https://<EXTERNAL-IP>` in your browser. Accept the certificate warning and login:
- Username: `admin`
- Password: the output from above

---

## Part 5 — GitOps Deployment with ArgoCD

### Step 1: Create Kubernetes manifests

**`k8s-manifests/deployment.yaml`:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gitops-app
  namespace: default
  labels:
    app: gitops-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: gitops-app
  template:
    metadata:
      labels:
        app: gitops-app
    spec:
      containers:
        - name: gitops-app
          image: <YOUR_ECR_URL>:latest
          ports:
            - containerPort: 5000
          livenessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              memory: "64Mi"
              cpu: "100m"
            limits:
              memory: "128Mi"
              cpu: "200m"
```

**`k8s-manifests/service.yaml`:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: gitops-app-service
  namespace: default
  labels:
    app: gitops-app
spec:
  type: LoadBalancer
  selector:
    app: gitops-app
  ports:
    - protocol: TCP
      port: 80
      targetPort: 5000
```

**`k8s-manifests/.argocd/application.yaml`:**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gitops-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/<YOUR_USERNAME>/gitops-argocd-eks.git
    targetRevision: HEAD
    path: k8s-manifests
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true      # removes resources deleted from repo
      selfHeal: true   # reverts manual changes made directly to the cluster
    syncOptions:
      - CreateNamespace=true
```

Replace `<YOUR_USERNAME>` with your GitHub username and `<YOUR_ECR_URL>` with your ECR URL.

### Step 2: Push and apply

```bash
git add k8s-manifests/
git commit -m "feat: add kubernetes manifests for gitops-app"
git push

kubectl apply -f k8s-manifests/.argocd/application.yaml
```

### Step 3: Verify everything is running

```bash
kubectl get application -n argocd
kubectl get pods -n default
kubectl get svc -n default
```

Expected:

```
NAME         SYNC STATUS   HEALTH STATUS
gitops-app   Synced        Healthy
```

Open the `EXTERNAL-IP` from `kubectl get svc` — your Flask app is live on the internet!

---

## Part 6 — Monitoring with Prometheus + Grafana

### Step 1: Add Helm repo and install stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin123 \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
```

### Step 2: Verify pods are running

```bash
kubectl get pods -n monitoring
```

Wait until all pods show `Running`. This may take 2–3 minutes.

### Step 3: Expose Grafana

```bash
kubectl patch svc monitoring-grafana -n monitoring -p '{"spec": {"type": "LoadBalancer"}}'
kubectl get svc monitoring-grafana -n monitoring
```

### Step 4: Access Grafana

Open `http://<GRAFANA-EXTERNAL-IP>` in your browser.

Login:
- Username: `admin`
- Password: `admin123`

### Step 5: Explore pre-built dashboards

Go to **Dashboards → Browse** and open:

- `Kubernetes / Compute Resources / Cluster` — cluster-wide CPU and memory
- `Kubernetes / USE Method / Node` — per-node resource utilization
- `Kubernetes / Compute Resources / Pod` — filter by namespace `default` to see your app

Prometheus is pre-connected as the default data source automatically by the Helm chart.

---

## Cleanup

Run this when you are done to avoid unexpected AWS charges:

```bash
# Delete Kubernetes resources first
kubectl delete -f k8s-manifests/.argocd/application.yaml
helm uninstall monitoring -n monitoring
kubectl delete namespace argocd monitoring

# Destroy all AWS infrastructure
cd terraform
terraform destroy
```

---

## Author

**Arash Mohammadi**
Junior DevOps & Cloud Engineer | AWS SAA | Terraform | Kubernetes

- GitHub: [github.com/ArashMHD91](https://github.com/ArashMHD91)
- Location: Berlin, Germany