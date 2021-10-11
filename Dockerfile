FROM python

RUN pip3 install flask requests

RUN mkdir /source /dest /fropbox

COPY ./client.py /fropbox/client.py
COPY ./server.py /fropbox/server.py
COPY ./file_segment.py /fropbox/file_segment.py
COPY ./server_wrapper.py /fropbox/server_wrapper.py
COPY ./test.py /fropbox/test.py

COPY ./dockerentrypoint.sh /

CMD ["sh", "dockerentrypoint.sh"]
