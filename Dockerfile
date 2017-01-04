FROM python:2.7.12
COPY kubewatcher.py kube_obj_parser.py /
RUN pip install requests
RUN git clone https://github.com/draios/python-sdc-client.git
CMD python kubewatcher.py
