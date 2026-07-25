/**
 * Cluster add-ons the application depends on.
 *
 *   ingress-nginx   the IngressClass the chart's Ingress objects reference
 *   metrics-server  the metrics.k8s.io API the HPA reads CPU from
 *
 * Both are the same charts a managed cluster would use; only their values are
 * kind-specific (hostPort instead of a cloud LoadBalancer, and a kubelet TLS
 * exception because kind's kubelet serves a self-signed certificate).
 */

resource "helm_release" "ingress_nginx" {
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = var.ingress_nginx_version
  namespace        = "ingress-nginx"
  create_namespace = true

  # Ingress controllers take a while to pass their admission-webhook checks;
  # waiting here means the app module never races against a missing webhook.
  wait    = true
  timeout = 600

  values = [yamlencode({
    controller = {
      # kind maps the control-plane node's :80/:443 to the host, so the
      # controller binds those ports directly instead of via a LoadBalancer.
      hostPort = {
        enabled = true
      }
      service = {
        type = "NodePort"
      }
      nodeSelector = {
        "ingress-ready" = "true"
      }
      tolerations = [{
        key      = "node-role.kubernetes.io/control-plane"
        operator = "Equal"
        effect   = "NoSchedule"
      }]
      publishService = {
        enabled = false
      }
      # Single controller pod on a single-node ingress tier.
      replicaCount = 1
      admissionWebhooks = {
        enabled = true
      }
    }
  })]
}

resource "helm_release" "metrics_server" {
  name             = "metrics-server"
  repository       = "https://kubernetes-sigs.github.io/metrics-server/"
  chart            = "metrics-server"
  version          = var.metrics_server_version
  namespace        = "kube-system"
  create_namespace = false

  wait    = true
  timeout = 300

  values = [yamlencode({
    # kind's kubelet presents a self-signed serving certificate that the
    # cluster CA does not sign. Without this flag metrics-server never becomes
    # ready and every HPA reports <unknown>/60%.
    args = ["--kubelet-insecure-tls"]
  })]
}
