pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: docker
    image: docker:24.0.7-cli
    command:
    - cat
    tty: true
    volumeMounts:
    - mountPath: /var/run/docker.sock
      name: docker-sock
  volumes:
  - name: docker-sock
    hostPath:
      path: /var/run/docker.sock
      type: Socket
'''
            defaultContainer 'docker'
        }
    }

    environment {
        IMAGE_NAME = 'meangene-bot:latest'
    }

    stages {
        stage('Build Docker Image') {
            steps {
                sh 'docker build -t $IMAGE_NAME .'
            }
        }
        stage('Save Docker Image') {
            steps {
                sh 'docker save $IMAGE_NAME -o meangene-bot.tar'
            }
        }
        stage('Load into MicroK8s') {
            steps {
                sh 'microk8s ctr image import meangene-bot.tar'
            }
        }
        stage('Restart Deployment') {
            steps {
                sh 'microk8s kubectl rollout restart deployment mean-gene-bot'
            }
        }
    }
}
