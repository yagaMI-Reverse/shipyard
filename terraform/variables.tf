variable "cluster_name" {
  description = "Name of the local kind cluster."
  type        = string
  default     = "shipyard"
}

variable "kubeconfig_path" {
  description = "Where the cluster's kubeconfig is written."
  type        = string
  default     = "./kubeconfig"
}

variable "worker_count" {
  description = "Worker nodes. Two is the minimum that makes topology spread and drains meaningful."
  type        = number
  default     = 2

  validation {
    condition     = var.worker_count >= 1 && var.worker_count <= 5
    error_message = "worker_count must be between 1 and 5."
  }
}

variable "ingress_http_port" {
  description = "Host port mapped to the ingress controller's :80. Port 80 itself is often taken on a workstation."
  type        = number
  default     = 8080
}

variable "ingress_https_port" {
  description = "Host port mapped to the ingress controller's :443."
  type        = number
  default     = 8443
}

variable "app_host" {
  description = "Ingress hostname. *.localtest.me always resolves to 127.0.0.1, so no hosts-file edit is needed."
  type        = string
  default     = "docuchat.localtest.me"
}

variable "api_image" {
  description = "Backend image reference (repository:tag)."
  type        = string
  default     = "shipyard/docuchat-api:dev"
}

variable "web_image" {
  description = "Frontend image reference (repository:tag)."
  type        = string
  default     = "shipyard/docuchat-web:dev"
}

variable "api_min_replicas" {
  description = "HPA floor for the API deployment."
  type        = number
  default     = 2
}

variable "api_max_replicas" {
  description = "HPA ceiling for the API deployment."
  type        = number
  default     = 8
}
