// MeteoSwiss Jenkinsfile to build and test a Flexpart-IFS container image.

class Globals {
    // constants
    static final String PROJECT = 'flexpart-ifs'
    static final String IMAGE_REPO = 'docker-intern-nexus.meteoswiss.ch'
    static final String IMAGE_REPO_PUBLIC = 'docker-public-nexus.meteoswiss.ch'
    static final String IMAGE_NAME = 'docker-intern-nexus.meteoswiss.ch/dispersionmodelling/flexpart-ifs'
    static final String IMAGE_NAME_PUBLIC = 'docker-public-nexus.meteoswiss.ch/dispersionmodelling/flexpart-ifs'
    static final String IMAGE_NAME_PUBLIC_PULL = 'container-registry.meteoswiss.ch/dispersionmodelling/flexpart-ifs'

    // sets the pipeline to execute all steps related to building the service
    static boolean build = false

    // sets to abort the pipeline if the Sonarqube QualityGate fails
    static boolean qualityGateAbortPipeline = false

    // sets the pipeline to execute all steps related to deployment of the service
    static boolean deploy = false

    // the image tag used for tagging the image
    static String imageTag = ''

    // the image tag used for pushing the image to the public Nexus repo
    static String imageTagPublic = ''

    // the image tag used for pulling the image from CSCS/externally
    static String imageTagPublicPull = ''

    // the service version
    static String version = ''

    // the Vault credititalId
    static String vaultCredentialId = ''

    // the Vault path
    static String vaultPath = ''
}

@Library('dev_tools@main') _
pipeline {
    agent {label 'podman'}

    parameters {
        choice(choices: ['Build', 'Deploy'],
            description: 'Build type',
            name: 'buildChoice')

        booleanParam(name: 'BUILD_BASE_IMAGE', defaultValue: false, description: 'Rebuilds the base image containing Spack dependencies')
    }

    options {
        // New jobs should wait until older jobs are finished
        disableConcurrentBuilds()
        // Discard old builds - keep 15
        buildDiscarder(logRotator(numToKeepStr: '15'))
        // Timeout the pipeline build after 1 hour
        timeout(time: 1, unit: 'HOURS')
        gitLabConnection('CollabGitLab')
    }

    environment {
        scannerHome = tool name: 'Sonarqube-certs-PROD', type: 'hudson.plugins.sonar.SonarRunnerInstallation'
        DOCKER_CONFIG = "$workspace/.docker"
        REGISTRY_AUTH_FILE = "$workspace/.containers/auth.json"
    }

    stages {
        stage('Preflight') {
            steps {
                updateGitlabCommitStatus name: 'Build', state: 'running'
                script {
                    echo 'Starting with Preflight'

                    // Determine the type of build
                    switch (params.buildChoice) {
                        case 'Build':
                            Globals.build = true
                            break
                        case 'Deploy':
                            Globals.deploy = true
                            break
                    }

                    if (Globals.build || Globals.deploy) {
                        echo 'Starting with calculating version'

                        def shortBranchName = env.BRANCH_NAME
                            .replaceAll("[^a-zA-Z0-9]+", "")
                            .take(30)
                            .toLowerCase()

                        try {
                            Globals.version = sh(
                                script: "git describe --tags --match 'v[0-9]*'",
                                returnStdout: true
                            ).trim()
                        } catch (err) {
                            def version = sh(
                                script: "git rev-parse --short HEAD",
                                returnStdout: true
                            ).trim()
                            Globals.version = "${shortBranchName}-${version}"
                        }

                        echo "Using version ${Globals.version}"

                        if (env.BRANCH_NAME == 'main') {
                            Globals.imageTag = "${Globals.IMAGE_NAME}:latest"
                            Globals.imageTagPublic = "${Globals.IMAGE_NAME_PUBLIC}:latest"
                            Globals.imageTagPublicPull = "${Globals.IMAGE_NAME_PUBLIC_PULL}:latest"
                        } else {
                            Globals.imageTag = "${Globals.IMAGE_NAME}:${shortBranchName}"
                            Globals.imageTagPublic = "${Globals.IMAGE_NAME_PUBLIC}:${shortBranchName}"
                            Globals.imageTagPublicPull = "${Globals.IMAGE_NAME_PUBLIC_PULL}:${shortBranchName}"
                        }

                        echo "Using container version ${Globals.imageTag}"
                    }
                }
            }
        }

        stage('Build Base dependencies image') {
            when { expression { params.BUILD_BASE_IMAGE } }
            steps {
                withCredentials([usernamePassword(
                                    credentialsId: 'github app credential for the meteoswiss github organization (limited to repositories used by APN)',
                                    usernameVariable: 'GITHUB_APP',
                                    passwordVariable: 'GITHUB_ACCESS_TOKEN'),
                                usernamePassword(
                                    credentialsId: 'openshift-nexus',
                                    passwordVariable: 'NXPASS',
                                    usernameVariable: 'NXUSER')
                            ]) {
                    echo "---- BUILDING BASE IMAGE ----"
                    sh """
                    podman build --pull -f Dockerfile.base --build-arg VERSION=${Globals.version} -t "${Globals.IMAGE_NAME}-base:${GIT_COMMIT}" .
                    """
                    echo "---- PUBLISH BASE IMAGE ----"
                    sh """
                    echo $NXPASS | podman login ${Globals.IMAGE_REPO} -u $NXUSER --password-stdin
                    podman tag ${Globals.IMAGE_NAME}-base:${GIT_COMMIT} ${Globals.IMAGE_NAME}-base:latest
                    podman push ${Globals.IMAGE_NAME}-base:${GIT_COMMIT}
                    podman push ${Globals.IMAGE_NAME}-base:latest
                    """
                }
            }
            post {
                cleanup {
                    sh "podman logout ${Globals.IMAGE_REPO} || true"
                }
            }
        }

        stage('Test') {
            when { expression { Globals.build } }
            environment {
                TEST_NODE = 'balfrin-ln003'
            }
            steps {
                withCredentials([usernamePassword(
                                    credentialsId: 'github app credential for the meteoswiss github organization (limited to repositories used by APN)',
                                    usernameVariable: 'GITHUB_APP',
                                    passwordVariable: 'GITHUB_ACCESS_TOKEN'),
                                usernamePassword(
                                    credentialsId: 'openshift-nexus',
                                    passwordVariable: 'NXPASS',
                                    usernameVariable: 'NXUSER')
                            ]) {
                    echo "Starting with Build image"
                    sh """
                    podman build --pull --build-arg TOKEN=${GITHUB_ACCESS_TOKEN} --build-arg COMMIT=${GIT_COMMIT} --build-arg VERSION=${Globals.version} --target tester -t ${Globals.imageTag}-tester .
                    mkdir -p test_reports && chmod a+rw test_reports
                    """
                    sh """ echo $NXPASS | podman login ${Globals.IMAGE_REPO_PUBLIC} -u $NXUSER --password-stdin
                    podman tag ${Globals.imageTag}-tester ${Globals.imageTagPublic}-tester
                    podman push ${Globals.imageTagPublic}-tester
                    """
                    echo "Starting with unit-testing including coverage"
                    sh """
                    ssh trajond@${TEST_NODE}.cscs.ch mkdir -p flexpart-ifs/test_reports
                    ssh trajond@${TEST_NODE}.cscs.ch sarus pull ${Globals.imageTagPublicPull}-tester
                    ssh trajond@${TEST_NODE}.cscs.ch "sarus run \
                        -e TEST_DATA=/scratch/test_data \
                        --mount=type=bind,source=/oprusers/trajond/flexpart-ifs/test_reports,destination=/scratch/test_reports \
                        --mount=type=bind,source=/oprusers/trajond/flexpart-ifs/test_data,destination=/scratch/test_data \
                        ${Globals.imageTagPublicPull}-tester \
                        sh -c '. ./test_ci.sh && run_tests_with_coverage'"
                    scp -rp trajond@${TEST_NODE}.cscs.ch:/oprusers/trajond/flexpart-ifs/test_reports/* test_reports && ls -l test_reports
                    """
                } 
            }
            post {
                always {
                    junit keepLongStdio: true, testResults: 'test_reports/junit.xml'
                }
                cleanup {
                    sh "podman logout ${Globals.IMAGE_REPO_PUBLIC} || true"
                }
            }
        }

        stage('Scan') {
            when { expression { Globals.build } }
            steps {
                script {
                    echo("---- LYNT ----")
                    sh "podman run --user \$(id -u) --rm -v \$(pwd)/test_reports:/scratch/test_reports ${Globals.imageTag}-tester sh -c '. ./test_ci.sh && run_pylint'"

                    try {
                        echo("---- TYPING CHECK ----")
                        sh "podman run --user \$(id -u) --rm -v \$(pwd)/test_reports:/scratch/test_reports ${Globals.imageTag}-tester sh -c '. ./test_ci.sh && run_mypy'"
                        recordIssues(qualityGates: [[threshold: 10, type: 'TOTAL', unstable: false]], tools: [myPy(pattern: 'test_reports/mypy.log')])
                    }
                    catch (err) {
                        error "Too many mypy issues, exiting now..."
                    }

                    echo("---- SONARQUBE ANALYSIS ----")
                    withSonarQubeEnv("Sonarqube-PROD") {
                        sh "cd utils && ${scannerHome}/bin/sonar-scanner"
                    }

                    echo("---- SONARQUBE QUALITY GATE ----")
                    timeout(time: 1, unit: 'HOURS') {
                        // Parameter indicates whether to set pipeline to UNSTABLE if Quality Gate fails
                        // true = set pipeline to UNSTABLE, false = don't
                        waitForQualityGate abortPipeline: Globals.qualityGateAbortPipeline
                    }
                }
            }
        }

        stage('Create Artifacts') {
            when { expression { Globals.build || Globals.deploy } }
            steps {
                script {
                    withCredentials([usernamePassword(
                        credentialsId: 'github app credential for the meteoswiss github organization (limited to repositories used by APN)',
                        usernameVariable: 'GITHUB_APP',
                        passwordVariable: 'GITHUB_ACCESS_TOKEN'
                    )]) {
                        echo "---- CREATE IMAGE ----"
                        sh """
                            podman build --pull \
                            --build-arg TOKEN=${GITHUB_ACCESS_TOKEN} \
                            --build-arg COMMIT=${GIT_COMMIT} \
                            --build-arg VERSION=${Globals.version} \
                            --target runner \
                            -t ${Globals.imageTag} .
                        """
                    }
                }
            }
        }

        stage('Publish Artifacts') {
            when { expression { Globals.deploy } }
            steps {
                script {
                    echo "---- PUBLISH IMAGE ----"
                    withCredentials([usernamePassword(credentialsId: 'openshift-nexus',
                        passwordVariable: 'NXPASS', usernameVariable: 'NXUSER')]) {
                        sh """
                        echo $NXPASS | podman login ${Globals.IMAGE_REPO} -u $NXUSER --password-stdin
                        podman push ${Globals.imageTag}
                        """
                    }
                }
            }
            post {
                cleanup {
                    sh "podman logout ${Globals.IMAGE_REPO} || true"
                }
            }
        }
    }

    post {
        cleanup {
            sh "podman image rm -f ${Globals.imageTag}-tester || true"
            sh "podman image rm -f ${Globals.imageTagPublic}-tester || true"
            sh "podman image rm -f ${Globals.imageTag} || true"
            sh "podman image rm -f ${Globals.IMAGE_NAME}-base || true"
        }
        success {
            echo 'Build succeeded'
        }
    }
}
