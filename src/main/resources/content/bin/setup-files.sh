#!/bin/sh

create_token() {
  echo $(cat /dev/urandom | base64 | tr -d "=+/" | dd bs=32 count=1 2> /dev/null)
}

if [ ! -d "$KUBERNETES_DATA_DIR" ]; then
	mkdir -p ${KUBERNETES_DATA_DIR}
fi

if [ ! -f "$KUBERNETES_DATA_DIR/basic_auth.csv" ]; then
	# Create basic token authorization
	echo "${KUBERNETES_ADMIN_PASSWORD},admin,admin" > ${KUBERNETES_DATA_DIR}/basic_auth.csv
fi

	# Create HTTPS certificates
	sudo groupadd -f -r ${KUBERNETES_CERT_GROUP}
	${CONTAINER_WORK_DIR}/bin/make-ca-cert.sh $(hostname -i)

if [ ! -f "$KUBERNETES_DATA_DIR/known_tokens.csv" ]; then
	# Create known tokens for service accounts
	echo "$(create_token),admin,admin" >> ${KUBERNETES_DATA_DIR}/known_tokens.csv
	echo "$(create_token),kubelet,kubelet" >> ${KUBERNETES_DATA_DIR}/known_tokens.csv
	echo "$(create_token),kube_proxy,kube_proxy" >> ${KUBERNETES_DATA_DIR}/known_tokens.csv
fi
