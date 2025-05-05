pipeline {
    agent {
        label 'docker-microk8s-agent'
    }

    environment {
        IMAGE_NAME = 'meangene-bot:latest'
        TAR_NAME = 'meangene-bot.tar'
    }

    stages {
        stage('Build Docker Image') {
            steps {
                container('docker-cli') {
                    echo "Building Docker image: ${IMAGE_NAME}"
                    sh 'docker build -t $IMAGE_NAME .'
                }
            }
        }

        stage('Save Docker Image') {
            steps {
                container('docker-cli') {
                    echo "Saving Docker image to tarball: ${TAR_NAME}"
                    sh 'docker save $IMAGE_NAME -o $TAR_NAME'
                }
            }
        }

        stage('Load into MicroK8s') {
            steps {
                container('docker-cli') {
                    echo "Importing image into MicroK8s container runtime"
                    sh 'microk8s ctr image import $TAR_NAME'
                }
            }
        }

        stage('Restart Deployment') {
            steps {
                container('docker-cli') {
                    echo "Restarting Kubernetes deployment"
                    sh 'microk8s kubectl rollout restart deployment mean-gene-bot'
                }
            }
        }
    }
}
