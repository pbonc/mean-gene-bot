pipeline {
    agent any

    environment {
        IMAGE_NAME = "meangene-bot"
        REMOTE_USER = "dar"
        REMOTE_HOST = "192.168.1.10"
        REMOTE_IMAGE_PATH = "/home/dar/${IMAGE_NAME}.tar"
    }

    stages {
        stage('Checkout') {
            steps {
                git 'git@github.com:pbonc/mean-gene-bot.git'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh "docker build -t ${IMAGE_NAME}:latest ."
            }
        }

        stage('Save Docker Image') {
            steps {
                sh "docker save ${IMAGE_NAME}:latest -o ${IMAGE_NAME}.tar"
            }
        }

        stage('Transfer to meangenebrain') {
            steps {
                sshagent (credentials: ['jenkins-bot']) {
                    sh "scp ${IMAGE_NAME}.tar ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_IMAGE_PATH}"
                }
            }
        }

        stage('Import and Restart on meangenebrain') {
            steps {
                sshagent (credentials: ['jenkins-bot']) {
                    sh """
                    ssh ${REMOTE_USER}@${REMOTE_HOST} '
                        sudo microk8s ctr image import ${REMOTE_IMAGE_PATH} &&
                        sudo microk8s kubectl rollout restart deployment mean-gene-bot
                    '
                    """
                }
            }
        }
    }

    post {
        cleanup {
            sh "rm -f ${IMAGE_NAME}.tar"
        }
    }
}
