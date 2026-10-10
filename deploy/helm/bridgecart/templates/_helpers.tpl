{{- define "bridgecart.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "bridgecart.backendEnv" -}}
- name: BRIDGECART_DATABASE_URL
  valueFrom:
    secretKeyRef: {name: {{ .Values.backend.databaseSecret | quote }}, key: database-url}
- {name: BRIDGECART_STAGE, value: {{ .Values.stage | quote }}}
- {name: BRIDGECART_COOKIE_SECURE, value: {{ .Values.backend.cookieSecure | quote }}}
- {name: BRIDGECART_COOKIE_SAMESITE, value: {{ .Values.backend.cookieSameSite | quote }}}
- {name: BRIDGECART_CORS_ORIGINS, value: {{ .Values.backend.corsOrigins | quote }}}
{{- end -}}

{{- define "bridgecart.backendDbEgress" -}}
- to:
    - podSelector:
        matchLabels:
          {{- include "bridgecart.selectorLabels" . | nindent 10 }}
          app.kubernetes.io/component: postgres
  ports: [{protocol: TCP, port: 5432}]
- to:
    - namespaceSelector:
        matchLabels: {kubernetes.io/metadata.name: kube-system}
      podSelector:
        matchLabels: {k8s-app: kube-dns}
  ports:
    - {protocol: UDP, port: 53}
    - {protocol: TCP, port: 53}
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

{{- define "bridgecart.wordpressEnv" -}}
- name: WORDPRESS_DB_HOST
  value: {{ include "bridgecart.fullname" . }}-mariadb:3306
- name: WORDPRESS_DB_NAME
  value: {{ .Values.store.mariadb.database | quote }}
- name: WORDPRESS_DB_USER
  value: {{ .Values.store.mariadb.user | quote }}
- name: WORDPRESS_DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.store.credentialsSecret | quote }}
      key: mariadb-password
{{- range $env, $key := dict "WORDPRESS_AUTH_KEY" "wordpress-auth-key" "WORDPRESS_SECURE_AUTH_KEY" "wordpress-secure-auth-key" "WORDPRESS_LOGGED_IN_KEY" "wordpress-logged-in-key" "WORDPRESS_NONCE_KEY" "wordpress-nonce-key" "WORDPRESS_AUTH_SALT" "wordpress-auth-salt" "WORDPRESS_SECURE_AUTH_SALT" "wordpress-secure-auth-salt" "WORDPRESS_LOGGED_IN_SALT" "wordpress-logged-in-salt" "WORDPRESS_NONCE_SALT" "wordpress-nonce-salt" }}
- name: {{ $env }}
  valueFrom:
    secretKeyRef:
      name: {{ $.Values.store.credentialsSecret | quote }}
      key: {{ $key }}
{{- end }}
{{- end -}}
