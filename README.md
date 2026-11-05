# Tareitas

Gestor local de tareas recurrentes para Windows. Está hecho con Python y Tkinter,
sin PySide ni Qt, y se entrega también como un único archivo ejecutable.

## Incluye

- Tareas recurrentes, periódicas y de una sola vez, con fecha de fin y horarios.
- Categorías con íconos, temas de color y modo oscuro.
- Calendario mensual, historial y recordatorios locales.
- Pomodoro personalizable y asociado opcionalmente a una tarea.
- Ejecutable listo para usar en [`release/Tareitas.exe`](release/Tareitas.exe).

Los datos de cada persona se guardan solo en su equipo, en
`%LOCALAPPDATA%\TareitasTk\tareas.db`; por eso no se suben al repositorio.

## Ejecutar el desarrollo

Para ejecutarla durante desarrollo:

```powershell
python main.py
```

## Generar un único ejecutable

```powershell
.\build.ps1
```

El resultado se genera en `%LOCALAPPDATA%\TareitasTkBuild\dist\Tareitas.exe`.
