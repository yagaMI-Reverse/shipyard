/**
 * A local Kubernetes cluster: one control-plane node plus workers.
 *
 * The control-plane node is labelled ingress-ready and publishes two host
 * ports; ingress-nginx is pinned to that node, so traffic reaches the cluster
 * on http://localhost:<ingress_http_port> with no LoadBalancer involved.
 */

resource "kind_cluster" "this" {
  name            = var.cluster_name
  node_image      = var.node_image != "" ? var.node_image : null
  kubeconfig_path = abspath(var.kubeconfig_path)
  wait_for_ready  = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"

      # ingress-nginx schedules onto this node via nodeSelector.
      kubeadm_config_patches = [
        <<-EOT
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
        EOT
      ]

      extra_port_mappings {
        container_port = 80
        host_port      = var.ingress_http_port
        protocol       = "TCP"
      }

      extra_port_mappings {
        container_port = 443
        host_port      = var.ingress_https_port
        protocol       = "TCP"
      }
    }

    dynamic "node" {
      for_each = range(var.worker_count)
      content {
        role = "worker"
      }
    }
  }
}
