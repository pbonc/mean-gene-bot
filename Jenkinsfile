pipeline {
    agent any

    environment {
        IMAGE_NAME = 'meangene-bot:latest'
        TAR_NAME = 'meangene-bot.tar'
        REMOTE_HOST = '192.168.1.10'
    }

    stages {
        stage('Build Docker Image') {
            steps {
                echo "Building Docker image: ${IMAGE_NAME}"
                sh 'docker build -t $IMAGE_NAME .'
            }
        }

        stage('Save Docker Image') {
            steps {
                echo "Saving Docker image to tarball: ${TAR_NAME}"
                sh 'docker save $IMAGE_NAME -o $TAR_NAME'
            }
        }

        stage('Copy Image to meangenebrain') {
            steps {
                sshagent(['meangenebrain-ssh']) {
                    sh 'scp -o StrictHostKeyChecking=no $TAR_NAME dar@192.168.1.10:/tmp/$TAR_NAME'
                }
            }
        }

        stage('Load Image into MicroK8s') {
            steps {
                sshagent(['meangenebrain-ssh']) {
                    sh 'ssh -o StrictHostKeyChecking=no dar@192.168.1.10 "microk8s ctr image import /tmp/$TAR_NAME"'
                }
            }
        }

        stage('Restart Deployment') {
            steps {
                sshagent(['meangenebrain-ssh']) {
                    sh 'ssh -o StrictHostKeyChecking=no dar@192.168.1.10 "microk8s kubectl rollout restart deployment mean-gene-bot"'
                }
            }
        }
    }
}
