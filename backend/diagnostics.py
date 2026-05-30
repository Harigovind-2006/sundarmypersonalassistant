import psutil

def run_diagnostics():
    """Runs CPU and Network diagnostics, returning spoken strings for any issues found."""
    messages = []
    
    # 1. CPU Audit
    high_cpu_procs = []
    try:
        # Give psutil a moment to calculate CPU percentages
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                cpu = proc.info['cpu_percent']
                # psutil cpu_percent can be higher than 100% on multi-core, 
                # but we'll use 80% as a threshold for a single process.
                if cpu is not None and cpu > 80.0:
                    name = proc.info['name']
                    if name != 'System Idle Process':
                        high_cpu_procs.append((proc.info['name'], proc.info['pid']))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        if high_cpu_procs:
            for name, pid in high_cpu_procs:
                messages.append(f"Process {name} with PID {pid} is consuming high CPU.")
    except Exception as e:
        messages.append("I encountered an error while checking the CPU.")
        
    # 2. Network Audit
    try:
        connections = psutil.net_connections(kind='inet')
        established_count = sum(1 for conn in connections if conn.status == 'ESTABLISHED')
        messages.append(f"There are {established_count} active external network connections.")
    except Exception as e:
        messages.append("I encountered an error while checking the network.")
        
    if not high_cpu_procs and 'encountered an error' not in " ".join(messages):
         messages.append("No suspicious CPU activity was detected. Your system appears clean.")
         
    return messages
