FROM python:3.12.10

WORKDIR /Nutrition-App
RUN python -m venv /opt/venv
ENV PATH ="/opt/venv/bin:$PATH"

RUN pip3 install --upgrade pip

COPY requirements.txt /Nutrition-App
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r docker_requirements.txt

COPY . /Nutrition-App

EXPOSE 5000
ENV FLASK_APP=RobertSUcks/app.py
CMD ["flask", "run", "--host=0.0.0.0"]
