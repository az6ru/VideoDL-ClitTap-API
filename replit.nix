{ pkgs }: {
  deps = [
    pkgs.ffmpeg
    pkgs.openssl
    pkgs.postgresql
  ];

  shellHook = ''
    # Убедитесь, что каталог данных существует
    if [ ! -d "/tmp/postgres_data" ]; then
      echo "Initializing PostgreSQL data directory..."
      initdb -D /tmp/postgres_data
    fi

    # Запуск сервера PostgreSQL
    echo "Starting PostgreSQL server..."
    pg_ctl -D /tmp/postgres_data -l /tmp/postgres_log start

    # Подождите, пока сервер запустится
    sleep 5

    # Создайте базу данных, если она не существует
    createdb -U postgres mydatabase || echo "Database already exists"
  '';
}
