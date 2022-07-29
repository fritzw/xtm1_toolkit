#include <arpa/inet.h>

#include <sys/types.h>
#include <sys/socket.h>
#include <stdio.h>
//#include <netdb.h>
#include <arpa/inet.h>
#include <unistd.h>
//#include <string.h>
#include <sys/select.h>
//#include <sys/time.h>
#include <stdlib.h>

#define IP_TO_INT(A, B, C, D) (((A) & 0xFF) << 24 | ((B) & 0xFF) << 16 | ((C) & 0xFF) << 8 | ((D) & 0xFF))

#define LISTEN_ADDRESS IP_TO_INT(127,0,0,1)
#define LISTEN_PORT 23
#define BUFFER_SIZE 1024
#define MAX_CLIENTS 1

#define MAX(A, B) ((A) >= (B) ? (A) : (B))

#ifdef NOISY
#define fprintf fprintf
#else
#define fprintf(...)
#endif

int create_socket()
{
    int server_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (-1 == setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &(int){1}, sizeof(int)))
        perror("setsockopt(SO_REUSEADDR) failed");
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(LISTEN_PORT);
    addr.sin_addr.s_addr = htonl(LISTEN_ADDRESS);

    int bindResult = bind(server_socket, (struct sockaddr *)&addr, sizeof(addr));
    if (bindResult == -1)
    {
        perror("bindResult");
        exit(1);
    }

    int listenResult = listen(server_socket, 1);
    if (listenResult == -1)
    {
        perror("listenResult");
        exit(1);
    }
    fprintf(stderr, "Server started, fd=%d\n", server_socket);
    return server_socket;
}

int wait_for_connection(int server_socket)
{
    struct sockaddr_in cliaddr;
    socklen_t addrlen = sizeof(cliaddr);
    int client_socket = accept(server_socket, (struct sockaddr *)&cliaddr, &addrlen);
    fprintf(stderr, "Accepted connection from IP %s, fd=%d\n", inet_ntoa(cliaddr.sin_addr), client_socket);
    return client_socket;
}

void bridge_streams(int stream1_read, int stream1_write, int stream2_read, int stream2_write)
{
    fd_set readfds;
    char buffer[BUFFER_SIZE];

    while (1)
    {
        fprintf(stderr, "Loop ~~~\n");
        FD_ZERO(&readfds);
        FD_SET(stream1_read, &readfds);
        FD_SET(stream2_read, &readfds);

        int max_fd = 0;
        max_fd = MAX(max_fd, stream1_read);
        max_fd = MAX(max_fd, stream2_read);

        int selectResult = select(max_fd + 1, &readfds, NULL, NULL, NULL);
        if (selectResult == -1)
        {
            perror("select");
        }

        if (FD_ISSET(stream1_read, &readfds))
        {
            int n_bytes = read(stream1_read, buffer, BUFFER_SIZE);
            if (n_bytes == -1)
            {
                perror("stream1 read error");
                break;
            }
            if (n_bytes == 0)
            {
                fprintf(stderr, "stream1 closed, shutting down");
                break;
            }
            write(stream2_write, buffer, n_bytes);
        }

        if (FD_ISSET(stream2_read, &readfds))
        {
            int n_bytes = read(stream2_read, buffer, BUFFER_SIZE);
            if (n_bytes == -1)
            {
                perror("stream2 read error");
                break;
            }
            if (n_bytes == 0)
            {
                fprintf(stderr, "stream2 closed, shutting down");
                break;
            }
            write(stream1_write, buffer, n_bytes);
        }
    }
}

int main()
{
    int server_socket = create_socket();

    int client_socket = wait_for_connection(server_socket);

    bridge_streams(client_socket, client_socket, STDIN_FILENO, STDOUT_FILENO);

    close(client_socket);
    close(server_socket);

    return 0;
}