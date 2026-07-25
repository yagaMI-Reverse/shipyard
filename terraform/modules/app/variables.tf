variable "release_name" {
  description = "Helm release name."
  type        = string
  default     = "shipyard"
}

variable "namespace" {
  description = "Namespace the application is deployed into."
  type        = string
  default     = "docuchat"
}

variable "chart_path" {
  description = "Path to the DocuChat chart directory."
  type        = string
}

variable "values_file" {
  description = "Base values file applied before the per-environment overrides below."
  type        = string
}

variable "app_host" {
  description = "Ingress hostname."
  type        = string
}

variable "api_image" {
  description = "Backend image as repository:tag."
  type        = string

  validation {
    condition     = length(split(":", var.api_image)) == 2
    error_message = "api_image must be in repository:tag form."
  }
}

variable "web_image" {
  description = "Frontend image as repository:tag."
  type        = string

  validation {
    condition     = length(split(":", var.web_image)) == 2
    error_message = "web_image must be in repository:tag form."
  }
}

variable "api_min_replicas" {
  description = "HPA floor."
  type        = number
  default     = 2
}

variable "api_max_replicas" {
  description = "HPA ceiling."
  type        = number
  default     = 8
}
