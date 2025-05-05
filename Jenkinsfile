pipeline {
    agent any  // Run this pipeline directly on the controller node

    environment {
        IMAGE_NAME = 'meangene-bot:latest'
        TAR_NAME = 'meangene-bot.tar'
    }

    stages {
        stage('Build Image with MicroK8s') {
            steps {
                echo "Building image: ${IMAGE_NAME} using MicroK8s"
                sh 'microk8s ctr image build -t $IMAGE_NAME .'
            }
        }

        stage('Save Docker Image') {
            steps {
                echo "Saving Docker image to tarball: ${TAR_NAME}"
                sh 'microk8s ctr images export $TAR_NAME $IMAGE_NAME'
            }
        }

        stage('Load into MicroK8s') {
            steps {
                echo "Importing image into MicroK8s container runtime"
                sh 'microk8s ctr image import $TAR_NAME'
            }
        }

        stage('Restart Deployment') {
            steps {
                echo "Restarting Kubernetes deployment"
                sh 'microk8s kubectl rollout restart deployment mean-gene-bot'
            }
        }
    }
}
