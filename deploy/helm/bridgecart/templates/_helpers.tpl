{{- define "bridgecart.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "bridgecart.fullname" -}}
{{- .Release.Name | trunc 52 | trimSuffix "-" -}}
{{- end -}}

{{- define "bridgecart.selectorLabels" -}}
app.kubernetes.io/name: {{ include "bridgecart.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "bridgecart.labels" -}}
{{ include "bridgecart.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
