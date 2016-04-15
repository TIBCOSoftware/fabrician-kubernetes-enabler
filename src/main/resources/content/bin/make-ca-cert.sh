#!/bin/sh

cert_ip=$1
extra_sans=${2:-}
cert_dir=${KUBERNETES_DATA_DIR}
cert_group=${KUBERNETES_CERT_GROUP}

mkdir -p "$cert_dir"

sans="IP:${cert_ip}"
if [[ -n "${extra_sans}" ]]; then
  sans="${sans},${extra_sans}"
fi

tmpdir=$(mktemp -d -t kubernetes_cacert.XXXXXX)
trap 'rm -rf "${tmpdir}"' EXIT
cd "${tmpdir}"

curl -L -O https://storage.googleapis.com/kubernetes-release/easy-rsa/easy-rsa.tar.gz > /dev/null 2>&1
tar xzf easy-rsa.tar.gz > /dev/null 2>&1

cd easy-rsa-master/easyrsa3
./easyrsa init-pki > /dev/null 2>&1
./easyrsa --batch "--req-cn=$cert_ip@`date +%s`" build-ca nopass > /dev/null 2>&1

./easyrsa --subject-alt-name="${sans}" build-server-full kubernetes-master nopass > /dev/null 2>&1

if [ ! -f "${cert_dir}/server.cert" ]; then
 cp -p pki/issued/kubernetes-master.crt "${cert_dir}/server.cert" > /dev/null 2>&1
 fi
 
 if [ ! -f "${cert_dir}/server.key" ]; then
cp -p pki/private/kubernetes-master.key "${cert_dir}/server.key" > /dev/null 2>&1
fi

./easyrsa build-client-full kubecfg nopass > /dev/null 2>&1
if [ ! -f "${cert_dir}/ca.crt" ]; then
cp -p pki/ca.crt "${cert_dir}/ca.crt"
fi

if [ ! -f "${cert_dir}/kubecfg.crt" ]; then
cp -p pki/issued/kubecfg.crt "${cert_dir}/kubecfg.crt"
fi

if [ ! -f "${cert_dir}/kubecfg.key" ]; then
cp -p pki/private/kubecfg.key "${cert_dir}/kubecfg.key"
fi

# Make server certs accessible to apiserver.
sudo chgrp $cert_group "${cert_dir}/server.key" "${cert_dir}/server.cert" "${cert_dir}/ca.crt"
sudo chmod 660 "${cert_dir}/server.key" "${cert_dir}/server.cert" "${cert_dir}/ca.crt"
