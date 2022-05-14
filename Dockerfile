FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update
RUN apt upgrade -y
RUN apt-get install -y ffmpeg
RUN apt install git-core python3 python3-pip -y
RUN pip3 install pipenv
RUN git clone https://github.com/rleyva/byrne-bot.git
WORKDIR byrne-bot
RUN pipenv install --deploy

ENTRYPOINT ["pipenv", "run", "python", "byrne_bot.py"]
