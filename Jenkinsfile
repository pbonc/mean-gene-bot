stage('Checkout') {
  steps {
    container('python') {
      sh '''
        eval `ssh-agent -s`
        ssh-add /home/jenkins/.ssh/id_ed25519
        git config --global knownHostsFile=/home/jenkins/.ssh/known_hosts
        git clone git@github.com:pbonc/mean-gene-bot.git
        cd mean-gene-bot
      '''
    }
  }
}
