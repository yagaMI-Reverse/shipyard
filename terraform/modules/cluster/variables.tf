variable "cluster_name" {
  description = "Cluster name; kubectl context becomes kind-<name>."
  type        = string
}

variable "kubeconfig_path" {
  description = "Path the kubeconfig is written to."
  type        = string
}

variable "worker_count" {
  description = "Number of worker nodes."
  type        = number
  default     = 2
}

variable "node_image" {
  description = "Pinned kindest/node image. Empty string uses the provider default."
  type        = string
  default     = ""
}

variable "ingress_http_port" {
  description = "Host port mapped to the control-plane node's :80."
  type        = number
  default     = 8080
}

variable "ingress_https_port" {
  description = "Host port mapped to the control-plane node's :443."
  type        = number
  default     = 8443
}
