###########################################
###########################################
## Dockerfile to run Mega-Linter ##
###########################################
###########################################

#############################################################################################
## Generated by .automation/build.py using descriptor files, please do not update manually ##
#############################################################################################
#FROM__START
FROM koalaman/shellcheck:latest as shellcheck
FROM borkdude/clj-kondo as clj-kondo
FROM hadolint/hadolint:latest-alpine as dockerfile-lint
FROM mstruebing/editorconfig-checker:latest as editorconfig-checker
FROM dotenvlinter/dotenv-linter:latest as dotenv-linter
FROM golangci/golangci-lint:latest as golangci-lint
FROM garethr/kubeval:latest as kubeval
FROM ghcr.io/assignuser/chktex-alpine:latest as chktex
FROM yoheimuta/protolint:latest as protolint
FROM ghcr.io/assignuser/lintr-lib:latest as lintr-lib
FROM wata727/tflint:latest as tflint
FROM accurics/terrascan:latest as terrascan
FROM alpine/terragrunt:latest as terragrunt
#FROM__END

##################
# Get base image #
##################
FROM python:alpine

###########################
# Get the build arguments #
###########################
ARG BUILD_DATE
ARG BUILD_REVISION
ARG BUILD_VERSION

#########################################
# Label the instance and set maintainer #
#########################################
LABEL com.github.actions.name="Mega-Linter" \
      com.github.actions.description="Lint your code base with GitHub Actions" \
      com.github.actions.icon="code" \
      com.github.actions.color="red" \
      maintainer="GitHub DevOps <github_devops@github.com>" \
      org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.revision=$BUILD_REVISION \
      org.opencontainers.image.version=$BUILD_VERSION \
      org.opencontainers.image.authors="GitHub DevOps <github_devops@github.com>" \
      org.opencontainers.image.url="https://github.com/github/mega-linter" \
      org.opencontainers.image.source="https://github.com/nvuillam/mega-linter" \
      org.opencontainers.image.documentation="https://github.com/github/mega-linter" \
      org.opencontainers.image.vendor="GitHub" \
      org.opencontainers.image.description="Lint your code base with GitHub Actions"

#################################################
# Set ENV values used for debugging the version #
#################################################
ENV BUILD_DATE=$BUILD_DATE
ENV BUILD_REVISION=$BUILD_REVISION
ENV BUILD_VERSION=$BUILD_VERSION

#######################################
# Copy scripts and rules to container #
#######################################
COPY lib /action/lib
COPY megalinter /megalinter
COPY megalinter/descriptors /megalinter-descriptors
COPY TEMPLATES /action/lib/.automation

#############################################################################################
## Generated by .automation/build.py using descriptor files, please do not update manually ##
#############################################################################################
#ARG__START
ARG PWSH_VERSION='latest'
ARG PWSH_DIRECTORY='/opt/microsoft/powershell'
ARG ARM_TTK_NAME='master.zip'
ARG ARM_TTK_URI='https://github.com/Azure/arm-ttk/archive/master.zip'
ARG ARM_TTK_DIRECTORY='/opt/microsoft'
ARG DART_VERSION='2.8.4'
ARG GLIBC_VERSION='2.31-r0'
ARG PSSA_VERSION='latest'
#ARG__END

####################
# Run APK installs #
####################

# APK Packages used by mega-linter core architecture
RUN apk add --update --no-cache \
    bash \
    coreutils \
    curl \
    file \
    gcc \
    git git-lfs\
    gnupg \
    icu-libs \
    jq \
    krb5-libs \
    libcurl libintl libssl1.1 libstdc++ \
    linux-headers \
    make \
    musl-dev \
    py3-setuptools \
    readline-dev

#############################################################################################
## Generated by .automation/build.py using descriptor files, please do not update manually ##
#############################################################################################
#APK__START
RUN apk add --update --no-cache \
                lttng-ust-dev \
                zlib \
                zlib-dev \
                go \
                openjdk8-jre \
                npm \
                nodejs-current \
                perl \
                perl-dev \
                php7 \
                php7-phar \
                php7-json \
                php7-mbstring \
                php-xmlwriter \
                php7-tokenizer \
                php7-ctype \
                php7-curl \
                php7-dom \
                php7-simplexml \
                ruby \
                ruby-dev \
                ruby-bundler \
                ruby-rdoc \
                ansible-lint \
                libc6-compat \
                R \
                R-dev \
                R-doc \
                libc-dev \
                libxml2-dev \
                libxml2-utils \
                libgcc
#APK__END

################################
# Installs python dependencies #
################################
RUN python /megalinter/setup.py install
#############################################################################################
## Generated by .automation/build.py using descriptor files, please do not update manually ##
#############################################################################################
#PIP__START
RUN pip3 install --no-cache-dir \
          cpplint \
          cfn-lint \
          pylint \
          black \
          flake8 \
          isort \
          snakemake \
          snakefmt \
          yamllint
#PIP__END

############################
# Install NPM dependencies #
#############################################################################################
## Generated by .automation/build.py using descriptor files, please do not update manually ##
#############################################################################################
#NPM__START
RUN npm install --no-cache \
                typescript \
                asl-validator \
                @coffeelint/cli \
                jscpd \
                stylelint \
                stylelint-config-standard \
                dockerfilelint \
                graphql-schema-linter \
                npm-groovy-lint \
                htmlhint \
                eslint \
                eslint-config-airbnb \
                eslint-config-prettier \
                eslint-config-standard \
                eslint-plugin-import \
                eslint-plugin-jest \
                eslint-plugin-node \
                eslint-plugin-prettier \
                eslint-plugin-promise \
                babel-eslint \
                standard@15.0.1 \
                jsonlint \
                eslint-plugin-react \
                markdownlint-cli \
                @stoplight/spectral@5.6.0 \
                cspell@4.1.3 \
                sql-lint \
                tekton-lint@0.4.2 \
                prettier \
                prettyjson \
                @typescript-eslint/eslint-plugin \
                @typescript-eslint/parser
#NPM__END

# Add node packages to path #
ENV PATH="/node_modules/.bin:${PATH}"

##############################
# Installs ruby dependencies #
#############################################################################################
## Generated by .automation/build.py using descriptor files, please do not update manually ##
#############################################################################################

#GEM__START
RUN echo 'gem: --no-document' >> ~/.gemrc && \
    gem install \
          scss_lint \
          puppet-lint \
          rubocop:0.82.0 \
          rubocop-github:0.16.0 \
          rubocop-performance:1.7.1 \
          rubocop-rails:2.5 \
          rubocop-rspec:1.41.0
#GEM__END

#############################################################################################
## Generated by .automation/build.py using descriptor files, please do not update manually ##
#############################################################################################
#OTHER__START
# CSHARP installation
RUN wget --tries=5 -O dotnet-install.sh https://dot.net/v1/dotnet-install.sh \
    && chmod +x dotnet-install.sh \
    && ./dotnet-install.sh --install-dir /usr/share/dotnet -channel Current -version latest

ENV PATH="${PATH}:/root/.dotnet/tools:/usr/share/dotnet"

# GO installation
ENV GOROOT=/usr/lib/go \
    GOPATH=/go

ENV PATH="$PATH":"$GOROOT"/bin:"$GOPATH"/bin
RUN mkdir -p ${GOPATH}/src ${GOPATH}/bin

# PHP installation
RUN wget --tries=5 -O phive.phar https://phar.io/releases/phive.phar \
    && wget --tries=5 -O phive.phar.asc https://phar.io/releases/phive.phar.asc \
    && PHAR_KEY_ID="0x9D8A98B29B2D5D79" \
    && ( gpg --keyserver ha.pool.sks-keyservers.net --recv-keys "$PHAR_KEY_ID" \
    || gpg --keyserver pgp.mit.edu --recv-keys "$PHAR_KEY_ID" \
    || gpg --keyserver keyserver.pgp.com --recv-keys "$PHAR_KEY_ID" ) \
    && gpg --verify phive.phar.asc phive.phar \
    && chmod +x phive.phar \
    && mv phive.phar /usr/local/bin/phive \
    && rm phive.phar.asc


# POWERSHELL installation
RUN mkdir -p ${PWSH_DIRECTORY} \
        && curl --retry 5 --retry-delay 5 -s https://api.github.com/repos/powershell/powershell/releases/${PWSH_VERSION} \
        | grep browser_download_url \
        | grep linux-alpine-x64 \
        | cut -d '"' -f 4 \
        | xargs -n 1 wget -O - \
        | tar -xzC ${PWSH_DIRECTORY} \
        && ln -sf ${PWSH_DIRECTORY}/pwsh /usr/bin/pwsh


# RUST installation
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# SCALA installation
RUN curl -fLo coursier https://git.io/coursier-cli && \
        chmod +x coursier


# arm-ttk installation
ENV ARM_TTK_PSD1="${ARM_TTK_DIRECTORY}/arm-ttk-master/arm-ttk/arm-ttk.psd1"
RUN curl --retry 5 --retry-delay 5 -sLO "${ARM_TTK_URI}" \
    && unzip "${ARM_TTK_NAME}" -d "${ARM_TTK_DIRECTORY}" \
    && rm "${ARM_TTK_NAME}" \
    && ln -sTf "${ARM_TTK_PSD1}" /usr/bin/arm-ttk \
    && chmod a+x /usr/bin/arm-ttk

# bash-exec installation
RUN printf '#!/bin/bash \n\nif [[ -x "$1" ]]; then exit 0; else echo "Error: File:[$1] is not executable"; exit 1; fi' > /usr/bin/bash-exec \
    && chmod +x /usr/bin/bash-exec


# shellcheck installation
COPY --from=shellcheck /bin/shellcheck /usr/bin/

# shfmt installation
ENV GO111MODULE=on
RUN go get mvdan.cc/sh/v3/cmd/shfmt

# clj-kondo installation
COPY --from=clj-kondo /usr/local/bin/clj-kondo /usr/bin/

# dotnet-format installation
RUN /usr/share/dotnet/dotnet tool install -g dotnet-format

# dartanalyzer installation
RUN wget --tries=5 -q -O /etc/apk/keys/sgerrand.rsa.pub https://alpine-pkgs.sgerrand.com/sgerrand.rsa.pub
RUN wget --tries=5 https://github.com/sgerrand/alpine-pkg-glibc/releases/download/${GLIBC_VERSION}/glibc-${GLIBC_VERSION}.apk
RUN apk add --no-cache glibc-${GLIBC_VERSION}.apk && rm glibc-${GLIBC_VERSION}.apk
RUN wget --tries=5 https://storage.googleapis.com/dart-archive/channels/stable/release/${DART_VERSION}/sdk/dartsdk-linux-x64-release.zip -O - -q | unzip -q - \
    && chmod +x dart-sdk/bin/dart* \
    && mv dart-sdk/bin/* /usr/bin/ && mv dart-sdk/lib/* /usr/lib/ && mv dart-sdk/include/* /usr/include/ \
    && rm -r dart-sdk/

# hadolint installation
COPY --from=dockerfile-lint /bin/hadolint /usr/bin/hadolint

# editorconfig-checker installation
COPY --from=editorconfig-checker /usr/bin/ec /usr/bin/editorconfig-checker

# dotenv-linter installation
COPY --from=dotenv-linter /dotenv-linter /usr/bin/

# golangci-lint installation
COPY --from=golangci-lint /usr/bin/golangci-lint /usr/bin/

# checkstyle installation
RUN CHECKSTYLE_LATEST=$(curl -s https://api.github.com/repos/checkstyle/checkstyle/releases/latest \
 | grep browser_download_url \
 | grep ".jar" \
 | cut -d '"' -f 4) \
&& curl --retry 5 --retry-delay 5 -sSL $CHECKSTYLE_LATEST \
--output /usr/bin/checkstyle


# ktlint installation
RUN curl --retry 5 --retry-delay 5 -sSLO https://github.com/pinterest/ktlint/releases/latest/download/ktlint && \
    chmod a+x ktlint && \
    mv "ktlint" /usr/bin/

# kubeval installation
COPY --from=kubeval /kubeval /usr/bin/

# chktex installation
COPY --from=chktex /usr/bin/chktex /usr/bin/
RUN cd ~ && touch .chktexrc

# luacheck installation
RUN wget --tries=5 https://www.lua.org/ftp/lua-5.3.5.tar.gz -O - -q | tar -xzf - \
    && cd lua-5.3.5 \
    && make linux \
    && make install \
    && cd .. && rm -r lua-5.3.5/ \
    && wget --tries=5 https://github.com/cvega/luarocks/archive/v3.3.1-super-linter.tar.gz -O - -q | tar -xzf - \
    && cd luarocks-3.3.1-super-linter \
    && ./configure --with-lua-include=/usr/local/include \
    && make \
    && make -b install \
    && cd .. && rm -r luarocks-3.3.1-super-linter/ \
    && luarocks install luacheck

# perlcritic installation
RUN curl --retry 5 --retry-delay 5 -sL https://cpanmin.us/ | perl - -nq --no-wget Perl::Critic

# php installation
RUN echo "No additional install for PHP built-in linter"

# phpcs installation
RUN phive install phpcs -g --trust-gpg-keys 31C7E470E2138192


# phpstan installation
RUN phive install phpstan -g --trust-gpg-keys CF1A108D0E7AE720


# psalm installation
RUN phive install psalm -g --trust-gpg-keys 8A03EA3B385DBAA1

# powershell installation
RUN pwsh -c 'Install-Module -Name PSScriptAnalyzer -RequiredVersion ${PSSA_VERSION} -Scope AllUsers -Force'

# protolint installation
COPY --from=protolint /usr/local/bin/protolint /usr/bin/

# lintr installation
COPY --from=lintr-lib /usr/lib/R/library/ /home/r-library
RUN R -e "install.packages(list.dirs('/home/r-library',recursive = FALSE), repos = NULL, type = 'source')"

# raku installation
RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && apk add --update --no-cache rakudo zef

# clippy installation
RUN rustup component add clippy

# scalafix installation
RUN ./coursier install scalafix --quiet --install-dir /usr/bin

# tflint installation
COPY --from=tflint /usr/local/bin/tflint /usr/bin/

# terrascan installation
COPY --from=terrascan /go/bin/terrascan /usr/bin/
RUN terrascan init

# terragrunt installation
COPY --from=terragrunt /usr/local/bin/terragrunt /usr/bin/

# dotnet-format installation
RUN echo "dotnet-format installation is managed from csharp descriptor"

#OTHER__END

######################
# Set the entrypoint #
######################
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x entrypoint.sh
RUN ls
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
