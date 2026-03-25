from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

# This automatically creates the /metrics endpoint
# and tracks all request durations and counts
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
    # Kubernetes liveness & readiness probe hits this
    # Must return 200 for the pod to be considered healthy
    return jsonify({
        "status": "healthy"
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
