pipeline {
    agent any

    environment {
        IMAGE_NAME = 'meangene-bot:latest'
    }

    stages {
        stage('Checkout') {
            steps {
                git credentialsId: 'jenkins-bot', url: 'git@github.com:pbonc/mean-gene-bot.git'
            }
        }

        stage('Build Image') {
            steps {
                sh 'docker build -t $IMAGE_NAME .'
            }
        }

        stage('Push to MicroK8s') {
            steps {
                sh 'docker save $IMAGE_NAME | sudo microk8s ctr image import -'
            }
        }

        stage('Restart Deployment') {
            steps {
                sh 'sudo microk8s kubectl rollout restart deployment mean-gene-bot'
            }
        }
    }
}
