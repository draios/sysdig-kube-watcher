FROM python:2.7.12
COPY kubewatcher.py kube_obj_parser.py requirements.txt /
RUN pip install -r requirements.txt
CMD python kubewatcher.py
