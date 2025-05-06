pipeline {
    agent any

    environment {
        SSH_KEY = "~/.ssh/jenkins_bot_key"
    }

    stages {
        stage('Update meangenebrain') {
            steps {
                echo "Updating meangenebrain..."
                sh '''
                    ssh -i $SSH_KEY -o StrictHostKeyChecking=no dar@localhost << 'EOF'
                    echo "[meangenebrain] Running apt update and upgrade"
                    sudo apt-get update && sudo apt-get upgrade -y
                    if [ -f /var/run/reboot-required ]; then
                        echo "[meangenebrain] Reboot required, rebooting now..."
                        sudo reboot
                    else
                        echo "[meangenebrain] No reboot required"
                    fi
                    EOF
                '''
            }
        }

        stage('Update meanpi') {
            steps {
                echo "Updating meanpi..."
                sh '''
                    ssh -i $SSH_KEY -o StrictHostKeyChecking=no ubuntu@192.168.1.20 << 'EOF'
                    echo "[meanpi] Running apt update and upgrade"
                    sudo apt-get update && sudo apt-get upgrade -y
                    if [ -f /var/run/reboot-required ]; then
                        echo "[meanpi] Reboot required, rebooting now..."
                        sudo reboot
                    else
                        echo "[meanpi] No reboot required"
                    fi
                    EOF
                '''
            }
        }
    }
}
