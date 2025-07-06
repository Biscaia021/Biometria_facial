############################################# IMPORTING ################################################
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog as tsd
from PIL import Image, ImageTk
import cv2
import os
import csv
import numpy as np
import pandas as pd
import datetime
import time
import serial  # Para comunicação com o servo
import atexit  # Para garantir o fechamento da porta serial
# --- ADICIONAR ESTAS IMPORTAÇÕES PARA O E-MAIL ---
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
# ---------------------------------------------

# Variável global para o ID do timer de fechamento automático da porta
auto_close_door_timer_id = None # Mantido como global

############################################# CONSTANTS ################################################
# --- Configurações do Servo ---
SERVO_SERIAL_PORT = "COM5"  # <<< --- Configure com a porta correta do seu Arduino
SERVO_BAUD_RATE = 9600
SERVO_OPEN_COMMAND = 'O'
SERVO_CLOSE_COMMAND = 'F'
SERVO_CONNECTION_TIMEOUT = 1 # Segundos para timeout da conexão serial
SERVO_ARDUINO_BOOT_DELAY = 2 # Segundos para aguardar o Arduino reiniciar

# --- Diretórios e Arquivos ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Diretório base do script
TRAINING_IMAGE_LABEL_DIR = os.path.join(BASE_DIR, "TrainingImageLabel")
STUDENT_DETAILS_DIR = os.path.join(BASE_DIR, "StudentDetails")
TRAINING_IMAGE_DIR = os.path.join(BASE_DIR, "TrainingImage")
ATTENDANCE_DIR = os.path.join(BASE_DIR, "Attendance") # 

HAARCASCADE_FILE = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
PASSWORD_FILE = os.path.join(TRAINING_IMAGE_LABEL_DIR, "psd.txt")
STUDENT_DETAILS_CSV = os.path.join(STUDENT_DETAILS_DIR, "StudentDetails.csv")
TRAINER_FILE = os.path.join(TRAINING_IMAGE_LABEL_DIR, "Trainner.yml")

# --- Configurações da Câmera e Reconhecimento ---
MAX_SAMPLES_PER_PERSON = 60 # Número de amostras de imagem por pessoa 
RECOGNITION_CONFIDENCE_THRESHOLD = 65 # Limiar de confiança para reconhecimento facial (menor é melhor) 
AUTO_CLOSE_DOOR_DELAY_SECONDS = 4 # Tempo em segundos para fechar a porta automaticamente

# --- Globais da GUI (usadas por várias funções) ---
window = None
clock_label = None
id_entry = None
name_entry = None
registration_status_label = None
total_registrations_label = None
attendance_treeview = None
change_password_window = None
old_password_entry = None
new_password_entry = None
confirm_new_password_entry = None
# --- Globais para o email ---
recipient_email_entry = None
domain_var = None
#----------------------------


servo_ser = None  # Objeto para a conexão serial

############################################# SERVO CONFIG & FUNCTIONS #################################

def init_servo_serial():
    """
    Inicializa a conexão serial com o servo motor (Arduino).
    Retorna True se a conexão for bem-sucedida, False caso contrário.
    """
    global servo_ser # 
    try:
        if servo_ser and servo_ser.is_open: # 
            print("Conexão serial do servo já ativa.") # 
            return True # 
        print(f"Tentando conectar ao servo em {SERVO_SERIAL_PORT}...") # 
        servo_ser = serial.Serial(SERVO_SERIAL_PORT, SERVO_BAUD_RATE, timeout=SERVO_CONNECTION_TIMEOUT) # 
        time.sleep(SERVO_ARDUINO_BOOT_DELAY)  # Aguarda o Arduino reiniciar # 
        print(f"Conectado ao servo em {SERVO_SERIAL_PORT}.") # 
        return True # 
    except serial.SerialException as e:
        print(f"Erro: Não foi possível conectar ao servo em {SERVO_SERIAL_PORT}. {e}") # 
        messagebox.showerror("Erro de Conexão com Servo",
                             f"Não foi possível conectar ao servo em {SERVO_SERIAL_PORT}.\n"
                             "Verifique a porta e a conexão do Arduino.\n"
                             "O controle da porta será desativado.") # 
        servo_ser = None # 
        return False # 

def send_servo_command(command):
    """
    Envia um comando para o servo motor via serial.
    Tenta reconectar se a conexão estiver inativa.
    Retorna True se o comando for enviado com sucesso, False caso contrário.
    """
    global servo_ser
    if not servo_ser or not servo_ser.is_open:
        print("Servo não conectado. Tentando conectar...")
        if not init_servo_serial():
            print("Falha ao conectar ao servo. Comando não enviado.")
            return False
    try:
        servo_ser.write(command.encode('utf-8'))
        print(f"Comando '{command}' enviado ao servo.")
        return True
    except serial.SerialException as e: # 
        print(f"Erro de comunicação serial ao enviar '{command}': {e}") # 
        return False # 
    except AttributeError:
        print(f"Erro: Objeto servo_ser é None ao tentar enviar comando '{command}'.")
        return False


def close_servo_serial():
    """
    Fecha a conexão serial com o servo e cancela timers pendentes.
    Chamada automaticamente ao sair do programa via atexit.
    """
    global servo_ser, auto_close_door_timer_id, window # auto_close_door_timer_id é global

    if auto_close_door_timer_id and window and window.winfo_exists():
        try:
            window.after_cancel(auto_close_door_timer_id)
            print(f"Timer de fechamento automático (ID: {auto_close_door_timer_id}) cancelado ao sair do programa.")
        except tk.TclError:
            print(f"Erro ao tentar cancelar timer (ID: {auto_close_door_timer_id}) ao sair do programa. Janela pode já estar destruída.")
        auto_close_door_timer_id = None

    if servo_ser and servo_ser.is_open:
        try:
            print(f"Enviando comando para {SERVO_CLOSE_COMMAND} (FECHAR) a porta antes de desconectar (atexit)...")
            send_servo_command(SERVO_CLOSE_COMMAND)
            time.sleep(0.5)

            print("Fechando porta serial do servo (atexit).") # 
            servo_ser.close() # 
            print("Desconectado do controlador de servo (atexit).") # 
        except serial.SerialException as e: # 
            print(f"Erro ao fechar porta serial ou enviar comando final (atexit): {e}")
        finally:
            servo_ser = None # 

atexit.register(close_servo_serial) # 

############################################# DIRECTORY & FILE SETUP #####################################
def assure_path_exists(path):
    if "." in os.path.basename(path):
        dir_path = os.path.dirname(path)
    else:
        dir_path = path

    if dir_path and not os.path.exists(dir_path): # Adicionado 'dir_path and' para checar se não é vazio
        os.makedirs(dir_path, exist_ok=True)
        print(f"Diretório criado: {dir_path}")

assure_path_exists(TRAINING_IMAGE_LABEL_DIR) # 
assure_path_exists(STUDENT_DETAILS_DIR) # 
assure_path_exists(TRAINING_IMAGE_DIR) # 
assure_path_exists(ATTENDANCE_DIR) # 

############################################# AUTOMATIC DOOR CONTROL #####################################

def auto_close_door():
    global auto_close_door_timer_id, window # auto_close_door_timer_id é global

    if not (window and window.winfo_exists()):
        print("Janela principal não existe mais. Cancelando fechamento automático da porta.")
        auto_close_door_timer_id = None
        return

    print("Tempo expirado. Enviando comando para fechar a porta automaticamente.")
    if send_servo_command(SERVO_CLOSE_COMMAND):
        print("Comando de fechar porta enviado automaticamente.")

    else:
        print("Falha ao enviar comando de fechar porta automaticamente.")

    auto_close_door_timer_id = None


def schedule_auto_close_door(delay_seconds=AUTO_CLOSE_DOOR_DELAY_SECONDS):
    global window, auto_close_door_timer_id # auto_close_door_timer_id é global

    if not (window and window.winfo_exists()):
        print("Janela principal não existe. Não é possível agendar fechamento da porta.")
        return

    if auto_close_door_timer_id:
        try:
            window.after_cancel(auto_close_door_timer_id)
            print(f"Timer de fechamento automático anterior (ID: {auto_close_door_timer_id}) cancelado.")
        except tk.TclError:
            print(f"Erro ao tentar cancelar timer anterior (ID: {auto_close_door_timer_id}). Pode já ter sido executado.")
        auto_close_door_timer_id = None

    print(f"Agendando fechamento automático da porta em {delay_seconds} segundos.")
    auto_close_door_timer_id = window.after(delay_seconds * 1000, auto_close_door)

############################################# GUI HELPER FUNCTIONS #######################################
def tick(): # 
    global clock_label
    if clock_label and clock_label.winfo_exists():
        current_time = time.strftime('%I:%M:%S %p') # 
        clock_label.config(text=current_time) # 
        clock_label.after(1000, tick) # 

def contact(): # 
    messagebox.showinfo(title='Contact us', message=" Entre em contato : 'rafael.biscaia10@gmail.com'")

def check_haarcascadefile(): # 
    if not os.path.isfile(HAARCASCADE_FILE): # 
        messagebox.showerror(title='File Missing',
                             message=f'{os.path.basename(HAARCASCADE_FILE)} is missing. ' # 
                                     'Please contact support or place it in the application directory.') # 
        if window:
            window.destroy() # 
        return False
    return True

############################################# PASSWORD MANAGEMENT ########################################
def save_password_action():
    global change_password_window, old_password_entry, new_password_entry, confirm_new_password_entry

    if not os.path.isfile(PASSWORD_FILE):
        messagebox.showerror("Erro", "Arquivo de senha não encontrado. Não é possível alterar.")
        if change_password_window: change_password_window.destroy()
        return

    with open(PASSWORD_FILE, "r") as pf:
        key_from_file = pf.read().strip()

    old_pwd = old_password_entry.get() # 
    new_pwd = new_password_entry.get() # 
    confirm_new_pwd = confirm_new_password_entry.get() # 

    if not old_pwd or not new_pwd or not confirm_new_pwd: # 
        messagebox.showerror(title='Erro', message='Todos os campos são obrigatórios.', parent=change_password_window) # 
        return # 

    if old_pwd == key_from_file: # 
        if new_pwd == confirm_new_pwd: # 
            with open(PASSWORD_FILE, "w") as pf_write: # 
                pf_write.write(new_pwd) # 
            messagebox.showinfo(title='Sucesso', message='Senha alterada com sucesso!', parent=change_password_window) # 
            if change_password_window: change_password_window.destroy() # 
        else:
            messagebox.showerror(title='Erro', message='As novas senhas não coincidem.', parent=change_password_window) # 
    else:
        messagebox.showerror(title='Senha Incorreta', message='Senha antiga incorreta.', parent=change_password_window) # 

def open_change_password_window(): # 
    global change_password_window, old_password_entry, new_password_entry, confirm_new_password_entry, window

    if not os.path.isfile(PASSWORD_FILE): # 
        new_initial_password = tsd.askstring('Senha Não Encontrada', # 
                                             'Nenhuma senha de administrador encontrada.\n'
                                             'Por favor, defina uma nova senha:',
                                             show='*', parent=window)
        if new_initial_password and new_initial_password.strip(): # 
            with open(PASSWORD_FILE, "w") as pf: # 
                pf.write(new_initial_password.strip()) # 
            messagebox.showinfo(title='Senha Registrada', # 
                                message='Nova senha de administrador registrada com sucesso!', parent=window)
        else: # 
            messagebox.showwarning(title='Nenhuma Senha Inserida', # 
                                   message='Senha não definida! A funcionalidade de administrador pode estar limitada.', parent=window)
        return # 

    change_password_window = tk.Toplevel(window) # 
    change_password_window.geometry("400x200") # 
    change_password_window.resizable(False, False) # 
    change_password_window.title("Alterar Senha") # 
    change_password_window.configure(background="white") # 
    change_password_window.grab_set() # 
    change_password_window.transient(window) # 

    tk.Label(change_password_window, text='Senha Antiga:', bg='white', font=('comic', 12, 'bold')).grid(row=0, column=0, padx=10, pady=5, sticky='w') # 
    old_password_entry = tk.Entry(change_password_window, width=25, fg="black", relief='solid', font=('comic', 12, 'bold'), show='*') # 
    old_password_entry.grid(row=0, column=1, padx=10, pady=5) # 
    tk.Label(change_password_window, text='Nova Senha:', bg='white', font=('comic', 12, 'bold')).grid(row=1, column=0, padx=10, pady=5, sticky='w') # 
    new_password_entry = tk.Entry(change_password_window, width=25, fg="black", relief='solid', font=('comic', 12, 'bold'), show='*') # 
    new_password_entry.grid(row=1, column=1, padx=10, pady=5) # 
    tk.Label(change_password_window, text='Confirmar Nova Senha:', bg='white', font=('comic', 12, 'bold')).grid(row=2, column=0, padx=10, pady=5, sticky='w') # 
    confirm_new_password_entry = tk.Entry(change_password_window, width=25, fg="black", relief='solid', font=('comic', 12, 'bold'), show='*') # 
    confirm_new_password_entry.grid(row=2, column=1, padx=10, pady=5) # 
    button_frame = tk.Frame(change_password_window, bg='white') # 
    button_frame.grid(row=3, column=0, columnspan=2, pady=10) # 
    save_btn = tk.Button(button_frame, text="Salvar", command=save_password_action, fg="black", bg="#00fcca", height=1, width=10, font=('comic', 10, 'bold')) # 
    save_btn.pack(side=tk.LEFT, padx=10) # 
    cancel_btn = tk.Button(button_frame, text="Cancelar", command=change_password_window.destroy, fg="black", bg="red", height=1, width=10, font=('comic', 10, 'bold')) # 
    cancel_btn.pack(side=tk.LEFT, padx=10) # 

def prompt_password_for_profile_save(): # 
    global window
    if not os.path.isfile(PASSWORD_FILE): # 
        new_pas = tsd.askstring('Senha não encontrada', # 
                                'Por favor, defina uma nova senha para proteger o treinamento de perfis:',
                                show='*', parent=window)
        if new_pas and new_pas.strip(): # 
            with open(PASSWORD_FILE, "w") as pf: # 
                pf.write(new_pas.strip()) # 
            messagebox.showinfo(title='Senha Registrada', # 
                                message='Nova senha registrada com sucesso! Agora você pode salvar perfis.',
                                parent=window)
        else: # 
            messagebox.showwarning(title='Nenhuma Senha Inserida', # 
                                   message='Senha não definida! Não é possível salvar o perfil.', # 
                                   parent=window)
        return # 

    with open(PASSWORD_FILE, "r") as pf: # 
        key_from_file = pf.read().strip() # 
    password_attempt = tsd.askstring('Senha Necessária', 'Digite a senha para Salvar Perfil:', show='*', parent=window) # 

    if password_attempt == key_from_file: # 
        train_images_action() # Chama a função de treinamento # 
    elif password_attempt is None: # 
        pass # 
    else: # 
        messagebox.showerror(title='Senha Incorreta', message='Senha incorreta. Perfil não salvo.', parent=window) # 

############################################# GUI INPUT CLEARING #####################################
def clear_id_entry(): # 
    global id_entry, registration_status_label
    if id_entry: id_entry.delete(0, 'end') # 
    if registration_status_label: registration_status_label.configure(text="1) Capture Imagens  >>>  2) Salve Perfil") # 

def clear_name_entry(): # 
    global name_entry, registration_status_label
    if name_entry: name_entry.delete(0, 'end') # 
    if registration_status_label: registration_status_label.configure(text="1) Capture Imagens  >>>  2) Salve Perfil") # 

############################################# REGISTRATION & IMAGE PROCESSING ##########################
def update_registration_count_display(): # 
    global total_registrations_label
    count = 0 # 
    if os.path.isfile(STUDENT_DETAILS_CSV): # 
        try:
            df = pd.read_csv(STUDENT_DETAILS_CSV) # 
            if 'SERIAL NO.' in df.columns: # 
                count = len(df[df['SERIAL NO.'].notna()]) # 
        except pd.errors.EmptyDataError: # 
            count = 0 # 
        except Exception as e: # 
            print(f"Erro ao ler {STUDENT_DETAILS_CSV} para contagem: {e}") # 
            count = 0 # 

    if total_registrations_label:
        total_registrations_label.configure(text=f'Total de Registros: {count}') # 
    return count # 

def take_images_action(): # 
    global id_entry, name_entry, registration_status_label, window
    if not check_haarcascadefile(): # 
        return

    student_id_str = id_entry.get().strip() # 
    student_name = name_entry.get().strip() # 

    if not student_id_str or not student_name: # 
        messagebox.showerror("Erro de Entrada", "ID e Nome não podem estar vazios.", parent=window) # 
        return # 
    if not student_id_str.isdigit(): # 
        messagebox.showerror("Erro de Entrada", "ID deve ser um número.", parent=window) # 
        return # 
    if not student_name.replace(' ', '').isalpha(): # 
        messagebox.showerror("Erro de Entrada", "Nome deve conter apenas letras e espaços.", parent=window) # 
        registration_status_label.configure(text="Nome inválido (apenas letras e espaços).") # 
        return # 

    columns = ['SERIAL NO.', 'ID', 'NAME'] # 
    next_serial_no = 1 # 
    df_students = None # 

    try:
        if os.path.isfile(STUDENT_DETAILS_CSV): # 
            try:
                df_students = pd.read_csv(STUDENT_DETAILS_CSV) # 
                if not df_students.empty and 'SERIAL NO.' in df_students.columns and df_students['SERIAL NO.'].notna().any(): # 
                    next_serial_no = df_students['SERIAL NO.'].max() + 1 # 
                if not df_students.empty and 'ID' in df_students.columns and student_id_str in df_students['ID'].astype(str).values: # 
                     messagebox.showerror("Erro", f"O ID de estudante '{student_id_str}' já existe.", parent=window) # 
                     return # 
            except pd.errors.EmptyDataError: # 
                df_students = pd.DataFrame(columns=columns) # 
            except KeyError: # 
                 messagebox.showerror("Erro de Arquivo", f"Arquivo {os.path.basename(STUDENT_DETAILS_CSV)} está malformado.", parent=window) # 
                 return # 
        else: # 
            with open(STUDENT_DETAILS_CSV, 'w', newline='') as csv_file: # 
                writer = csv.writer(csv_file) # 
                writer.writerow(columns) # 
            df_students = pd.DataFrame(columns=columns) # 
    except Exception as e: # 
        messagebox.showerror("Erro de Arquivo", f"Não foi possível ler/escrever os detalhes dos estudantes: {e}", parent=window) # 
        return # 

    cam = cv2.VideoCapture(0) # 
    if not cam.isOpened(): # 
        messagebox.showerror("Erro de Câmera", "Não foi possível abrir a câmera.", parent=window) # 
        return # 

    detector = cv2.CascadeClassifier(HAARCASCADE_FILE) # 
    sample_num = 0 # 

    window_title_capture = "Capturando Imagens - Pressione Q para Sair" # 
    cv2.namedWindow(window_title_capture, cv2.WINDOW_AUTOSIZE) # 

    try:
        while True: # 
            ret, img = cam.read() # 
            if not ret: # 
                messagebox.showerror("Erro de Câmera", "Falha ao capturar imagem da câmera.", parent=window) # 
                break # 

            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # 
            faces = detector.detectMultiScale(gray_img, scaleFactor=1.3, minNeighbors=5, minSize=(100,100)) # 
            display_img = img.copy() # 

            for (x, y, w, h) in faces: # 
                cv2.rectangle(display_img, (x, y), (x + w, y + h), (255, 0, 0), 2) # 
                if sample_num < MAX_SAMPLES_PER_PERSON: # 
                    sample_num += 1 # 
                    img_filename = f"{student_name}.{next_serial_no}.{student_id_str}.{sample_num}.jpg" # 
                    face_roi_gray = gray_img[y:y + h, x:x + w] # 
                    cv2.imwrite(os.path.join(TRAINING_IMAGE_DIR, img_filename), face_roi_gray) # 

                progress_text = f"Amostras: {sample_num}/{MAX_SAMPLES_PER_PERSON}" # 
                cv2.putText(display_img, progress_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2) # 

            cv2.imshow(window_title_capture, display_img) # 

            key = cv2.waitKey(100) & 0xFF # 
            if key == ord('q') or key == 27: # 
                break # 
            if sample_num >= MAX_SAMPLES_PER_PERSON: # 
                break # 
    finally:
        cam.release() # 
        cv2.destroyAllWindows() # 

    if sample_num > 0: # 
        res_msg = f"Imagens Capturadas para ID: {student_id_str} (Serial Interno: {next_serial_no})" # 
        row_to_add = [next_serial_no, student_id_str, student_name] # 
        try:
            with open(STUDENT_DETAILS_CSV, 'a+', newline='') as csv_file: # 
                writer = csv.writer(csv_file) # 
                writer.writerow(row_to_add) # 
            registration_status_label.configure(text=res_msg) # 
            update_registration_count_display() # 
        except Exception as e: # 
             messagebox.showerror("Erro de Arquivo", f"Não foi possível salvar os detalhes do estudante: {e}", parent=window) # 
             registration_status_label.configure(text="Erro ao salvar detalhes.") # 
    else: # 
        registration_status_label.configure(text="Nenhuma imagem capturada. Face não detectada ou processo interrompido.") # 

def train_images_action(): # 
    global registration_status_label, window
    if not check_haarcascadefile(): # 
        return

    recognizer = cv2.face.LBPHFaceRecognizer_create() # 
    faces, serial_ids_for_training = get_images_and_labels(TRAINING_IMAGE_DIR) # 

    if not faces or not serial_ids_for_training: # 
        messagebox.showerror(title='Sem Dados', # 
                             message='Nenhuma imagem encontrada para treinamento ou IDs não puderam ser extraídos.\n' # 
                                     'Por favor, registre alguém primeiro e capture as imagens.', # 
                             parent=window)
        return # 

    if len(set(serial_ids_for_training)) < 1: # 
        messagebox.showerror(title='Dados Insuficientes', # 
                             message='É necessário registrar pelo menos uma pessoa com imagens para o treinamento.', # 
                             parent=window)
        return # 

    try:
        recognizer.train(faces, np.array(serial_ids_for_training)) # 
    except cv2.error as e: # 
        error_message = f'Não foi possível treinar o reconhecedor: {e}\n' # 
        if "src.size() > 0" in str(e) or "empty" in str(e).lower(): # 
             error_message += "Verifique se há imagens de treinamento válidas.\n" # 
        if "labels" in str(e).lower() and "int" in str(e).lower(): # 
             error_message += "Os IDs (labels) para treinamento devem ser inteiros.\n" # 
        if len(set(serial_ids_for_training)) < 2 and "two" in str(e).lower(): # 
            error_message += "Alguns algoritmos de treinamento podem requerer pelo menos duas pessoas diferentes registradas.\n" # 
        messagebox.showerror(title='Erro de Treinamento', message=error_message, parent=window) # 
        return # 
    except Exception as e: # 
        messagebox.showerror(title='Erro de Treinamento', # 
                             message=f'Um erro inesperado ocorreu durante o treinamento: {e}', # 
                             parent=window)
        return # 

    try:
        recognizer.save(TRAINER_FILE) # 
    except Exception as e: # 
        messagebox.showerror(title='Erro ao Salvar', # 
                             message=f'Não foi possível salvar o arquivo de treinamento {os.path.basename(TRAINER_FILE)}: {e}', # 
                             parent=window)
        return # 

    num_trained_unique_ids = len(set(serial_ids_for_training)) # 
    res = f"Perfil Salvo! Treinado para {num_trained_unique_ids} indivíduo(s) único(s)." # 
    registration_status_label.configure(text=res) # 
    messagebox.showinfo(title='Sucesso', message=res, parent=window) # 

def get_images_and_labels(path_to_images): # 
    image_paths = [os.path.join(path_to_images, f) for f in os.listdir(path_to_images) # 
                   if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
    faces = [] # 
    serial_ids = [] # 

    for image_path in image_paths: # 
        try:
            pil_image = Image.open(image_path).convert('L') # 
            image_np = np.array(pil_image, 'uint8') # 

            filename_parts = os.path.basename(image_path).split(".") # 
            if len(filename_parts) >= 4: # 
                internal_serial_id = int(filename_parts[1]) # 
                faces.append(image_np) # 
                serial_ids.append(internal_serial_id) # 
            else: # 
                print(f"Aviso: Pulando arquivo com formato de nome inesperado: {image_path}") # 
        except ValueError: # 
            print(f"Aviso: Erro ao converter ID para inteiro no arquivo: {image_path}. Pulando.") # 
        except Exception as e: # 
            print(f"Erro ao processar imagem {image_path}: {e}. Pulando.") # 

    return faces, serial_ids # 

###########################################################################################
#                               TRACKING & ATTENDANCE LOGIC                             #
###########################################################################################

def track_images_action(): # 
    global attendance_treeview, window, auto_close_door_timer_id # Declarar auto_close_door_timer_id como global AQUI

    if not check_haarcascadefile(): return # 
    if attendance_treeview: # 
        for item in attendance_treeview.get_children(): # 
            attendance_treeview.delete(item) # 

    servo_enabled = init_servo_serial() # 
    if not servo_enabled: # 
        messagebox.showwarning("Aviso Servo", # 
                               "Controle da porta desativado devido a falha na conexão com o servo.\n" # 
                               "O sistema de presença continuará sem controle de porta.", # 
                               parent=window)

    recognizer = cv2.face.LBPHFaceRecognizer_create() # 
    if not os.path.isfile(TRAINER_FILE): # 
        messagebox.showerror(title='Arquivo de Treinamento Ausente', # 
                             message=f'{os.path.basename(TRAINER_FILE)} não encontrado. Por favor, Salve um Perfil primeiro.', # 
                             parent=window)
        return # 
    recognizer.read(TRAINER_FILE) # 

    face_cascade = cv2.CascadeClassifier(HAARCASCADE_FILE) # 

    if not os.path.isfile(STUDENT_DETAILS_CSV): # 
        messagebox.showerror(title='Detalhes Ausentes', # 
                             message=f'{os.path.basename(STUDENT_DETAILS_CSV)} está ausente. Não é possível mapear rostos para nomes.', # 
                             parent=window)
        return # 
    try:
        df_students = pd.read_csv(STUDENT_DETAILS_CSV) # 
        if df_students.empty: # 
            messagebox.showerror(title='Detalhes Vazios', # 
                                 message=f'{os.path.basename(STUDENT_DETAILS_CSV)} está vazio. Registre estudantes primeiro.', # 
                                 parent=window)
            return # 
        if not all(col in df_students.columns for col in ['SERIAL NO.', 'ID', 'NAME']): # 
            messagebox.showerror(title='Arquivo de Detalhes Inválido', # 
                                 message=f'{os.path.basename(STUDENT_DETAILS_CSV)} não contém as colunas esperadas (SERIAL NO., ID, NAME).', # 
                                 parent=window)
            return # 
    except Exception as e: # 
        messagebox.showerror(title='Erro ao Ler Detalhes', # 
                             message=f'Erro ao ler {os.path.basename(STUDENT_DETAILS_CSV)}: {e}', # 
                             parent=window)
        return # 

    cam = cv2.VideoCapture(0) # 
    if not cam.isOpened(): # 
        messagebox.showerror("Erro de Câmera", "Não foi possível abrir a câmera.", parent=window) # 
        return # 

    font = cv2.FONT_HERSHEY_SIMPLEX # 
    recognized_today_session = {} # 
    door_was_opened_this_session = False # Flag para rastrear se a porta foi aberta

    window_title_tracking = "Pressione Q para Sair" # 
    cv2.namedWindow(window_title_tracking, cv2.WINDOW_AUTOSIZE) # 

    try:
        while True: # 
            ret, frame = cam.read() # 
            if not ret: # 
                messagebox.showerror("Erro de Câmera", "Falha ao capturar imagem da câmera.", parent=window) # 
                break # 

            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) # 
            faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.2, minNeighbors=5, minSize=(100, 100)) # 
            display_frame = frame.copy() # 

            for (x, y, w, h) in faces: # 
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (225, 0, 0), 2) # 

                predicted_serial_no, confidence = recognizer.predict(gray_frame[y:y + h, x:x + w]) # 

                name_display = "Desconhecido" # 
                student_id_display = "N/A" # 

                if confidence < RECOGNITION_CONFIDENCE_THRESHOLD: # 
                    student_info = df_students[df_students['SERIAL NO.'] == predicted_serial_no] # 

                    if not student_info.empty: # 
                        name_display = student_info['NAME'].values[0] # 
                        student_id_display = str(student_info['ID'].values[0]) # 

                        if servo_enabled: # 
                            print(f"Acesso concedido para: {name_display}. Enviando comando para abrir a porta.") # 
                            if send_servo_command(SERVO_OPEN_COMMAND): # 
                                schedule_auto_close_door() # 
                                door_was_opened_this_session = True # MARCA QUE A PORTA FOI ABERTA
                        current_time_obj = datetime.datetime.now() # 
                        date_str = current_time_obj.strftime('%d-%m-%Y') # 
                        time_str = current_time_obj.strftime('%I:%M:%S %p') # 

                        if (student_id_display, date_str) not in recognized_today_session: # 
                            recognized_today_session[(student_id_display, date_str)] = time_str # 
                            print(f"Presença registrada para {name_display} (ID: {student_id_display}) em {date_str} às {time_str}") # 
                    else: # 
                        name_display = "Face Conhecida, ID não Cadastrado" # 
                        student_id_display = f"Serial: {predicted_serial_no}" # 
                else: # 
                    name_display = "Desconhecido" # 

                cv2.putText(display_frame, f"{name_display} (ID:{student_id_display})", (x, y + h + 20), font, 0.6, (255, 255, 255), 1) # 
                conf_text_color = (0,0,255) if confidence >= RECOGNITION_CONFIDENCE_THRESHOLD else (0,255,0) # 
                cv2.putText(display_frame, f"Conf: {round(confidence,2)}", (x, y-5), font, 0.5, conf_text_color, 1) # 

            cv2.imshow(window_title_tracking, display_frame) # 

            key = cv2.waitKey(1) & 0xFF # 
            if key == ord('q') or key == 27: # 
                break # 
    finally:
        cam.release() # 
        cv2.destroyAllWindows() # 

        # --- LÓGICA PARA FECHAR A PORTA AO SAIR COM 'Q' ---
        if door_was_opened_this_session and servo_enabled: # 
            print("Saindo do reconhecimento (tecla Q pressionada). Fechando a porta manualmente...") # 

            # Cancela qualquer timer de fechamento automático pendente, pois vamos fechar manualmente agora.
            if auto_close_door_timer_id: # Verifica se existe um timer # 
                if window and window.winfo_exists(): # Verifica se a janela principal ainda existe # 
                    try:
                        window.after_cancel(auto_close_door_timer_id) # 
                        print(f"Timer de fechamento automático (ID: {auto_close_door_timer_id}) cancelado ao sair do reconhecimento.") # 
                    except tk.TclError: # 
                        print(f"Erro ao cancelar timer (ID: {auto_close_door_timer_id}) ao sair do reconhecimento - janela pode não existir mais.") # 
                auto_close_door_timer_id = None # Anula o ID do timer globalmente para evitar execuções futuras # 

            if send_servo_command(SERVO_CLOSE_COMMAND): # 
                print("Porta fechada com sucesso ao sair do reconhecimento.") # 
            else: # 
                print("Falha ao enviar comando para fechar a porta ao sair do reconhecimento.") # 
        # ----------------------------------------------------

    if recognized_today_session: # 
        save_attendance_to_csv(recognized_today_session, df_students) # 
        populate_treeview_from_csv() # 

def save_attendance_to_csv(recognized_this_session, df_all_students): # 
    if not recognized_this_session: # 
        return

    first_entry_date_str = next(iter(recognized_this_session.keys()))[1] # 
    attendance_csv_filename = f"Attendance_{first_entry_date_str}.csv" # 
    attendance_csv_path = os.path.join(ATTENDANCE_DIR, attendance_csv_filename) # 

    col_names_attendance = ['Registered_ID', 'Name', 'Date', 'Time'] # 

    existing_records_in_file = set() # 
    if os.path.isfile(attendance_csv_path): # 
        try:
            df_existing_attendance = pd.read_csv(attendance_csv_path) # 
            if not df_existing_attendance.empty: # 
                for _, row in df_existing_attendance.iterrows(): # 
                    existing_records_in_file.add((str(row['Registered_ID']), row['Date'])) # 
        except Exception as e: # 
            print(f"Erro ao ler arquivo de presença existente {attendance_csv_path}: {e}") # 

    try:
        with open(attendance_csv_path, 'a+', newline='') as csv_file: # 
            writer = csv.writer(csv_file) # 
            if os.path.getsize(attendance_csv_path) == 0 and not existing_records_in_file: # 
                writer.writerow(col_names_attendance) # 

            for (student_id, att_date), att_time in recognized_this_session.items(): # 
                if (student_id, att_date) not in existing_records_in_file: # 
                    student_info_for_csv = df_all_students[df_all_students['ID'].astype(str) == student_id] # 
                    att_name = student_info_for_csv['NAME'].values[0] if not student_info_for_csv.empty else "Nome N/A" # 

                    writer.writerow([student_id, att_name, att_date, att_time]) # 
                    print(f"Salvo no CSV: ID {student_id}, Nome {att_name}, Data {att_date}, Hora {att_time}") # 
    except IOError as e: # 
        print(f"Erro de I/O ao salvar presença no CSV: {e}") # 
        messagebox.showerror("Erro de Arquivo", f"Não foi possível salvar o arquivo de presença: {e}", parent=window) # 
    except Exception as e: # 
        print(f"Erro inesperado ao salvar presença no CSV: {e}") # 
        messagebox.showerror("Erro Inesperado", f"Ocorreu um erro ao salvar a presença: {e}", parent=window) # 

def populate_treeview_from_csv(): # 
    global attendance_treeview, window
    if not attendance_treeview: return # 

    for item in attendance_treeview.get_children(): # Limpa a treeview # 
        attendance_treeview.delete(item) # 

    current_date_filename_part = datetime.datetime.now().strftime('%d-%m-%Y') # 
    attendance_csv_path = os.path.join(ATTENDANCE_DIR, f"Attendance_{current_date_filename_part}.csv") # 

    if os.path.isfile(attendance_csv_path): # 
        try:
            with open(attendance_csv_path, 'r', newline='') as csv_file: # 
                reader = csv.reader(csv_file) # 
                header = next(reader, None) # Pula o cabeçalho # 

                displayed_in_treeview_today = set() # (student_id, date) para evitar duplicatas na exibição # 

                if header: # Garante que o arquivo não está completamente vazio após o cabeçalho # 
                    for row_num, line_parts in enumerate(reader, 1): # Começa contagem de linha em 1 para logs # 
                        if len(line_parts) >= 4: # 
                            reg_id_val, name_val, date_val, time_val = line_parts[0], line_parts[1], line_parts[2], line_parts[3] # 

                            if (reg_id_val, date_val) not in displayed_in_treeview_today: # 
                                attendance_treeview.insert('', 'end', text=reg_id_val, values=(name_val, date_val, time_val)) # 
                                displayed_in_treeview_today.add((reg_id_val, date_val)) # 
                        else: # 
                            print(f"Aviso: Linha {row_num+1} no CSV de presença tem formato incorreto: {line_parts}") # 
        except StopIteration: # Arquivo CSV tem apenas cabeçalho ou está vazio # 
             print(f"Arquivo de presença {os.path.basename(attendance_csv_path)} está vazio ou contém apenas cabeçalho.") # 
        except Exception as e: # 
            print(f"Erro ao ler ou analisar CSV de presença para treeview: {e}") # 
            messagebox.showerror("Erro na Treeview", f"Não foi possível carregar presença na tabela: {e}", parent=window) # 

############################################# DATA DELETION FUNCTIONS ###################################

# --- FUNÇÃO DE ENVIO DE EMAIL COMPLETA ---
def send_email(): # 
    global recipient_email_entry, domain_var, window # Adiciona as globais da GUI para email

    recipient_email_user = recipient_email_entry.get().strip() # 
    selected_domain = domain_var.get() # 

    if not recipient_email_user: # 
        messagebox.showerror(title='Error', message='Please enter the recipient\'s email username.', parent=window) # 
        return # 

    full_recipient_email = f"{recipient_email_user}@{selected_domain}" # 

    # ATENÇÃO: Substitua com suas credenciais reais de e-mail
    # É altamente recomendável usar senhas de aplicativo se o seu provedor de e-mail (como Gmail) as suportar.
    from_email = "seu_email_remetente@gmail.com"  # SEU EMAIL AQUI 
    password = "sua_senha_de_aplicativo_ou_normal"    # SUA SENHA AQUI 

    if from_email == "seu_email_remetente@gmail.com" or password == "sua_senha_de_aplicativo_ou_normal": # 
        messagebox.showwarning("Configuração Necessária", # 
                               "As credenciais do remetente de e-mail não estão configuradas.\n" # 
                               "Por favor, configure-as no script (variáveis 'from_email' e 'password' na função send_email).", # 
                               parent=window)
        return # 

    msg = MIMEMultipart() # 
    msg['From'] = from_email # 
    msg['To'] = full_recipient_email # 
    
    current_date_str = datetime.datetime.now().strftime('%d-%m-%Y') # 
    current_time_str = time.strftime('%I:%M:%S %p') # 
    msg['Subject'] = f"Relatório de Presença - Data: {current_date_str}, Hora: {current_time_str}" # 

    body = f"Prezado(a),\n\nSegue em anexo o relatório de presença para {current_date_str}.\n\nAtenciosamente,\nSistema de Presença" # 
    msg.attach(MIMEText(body, 'plain')) # 

    attendance_filename_to_send = f"Attendance_{current_date_str}.csv" # 
    attachment_path = os.path.join(ATTENDANCE_DIR, attendance_filename_to_send) # 

    if not os.path.isfile(attachment_path): # 
        messagebox.showerror(title='Erro', message=f'Arquivo de anexo "{attendance_filename_to_send}" não encontrado.', parent=window) # 
        return # 

    try:
        with open(attachment_path, "rb") as attachment: # 
            part = MIMEBase('application', 'octet-stream') # 
            part.set_payload(attachment.read()) # 
        encoders.encode_base64(part) # 
        part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(attachment_path)}") # 
        msg.attach(part) # 
    except Exception as e: # 
        messagebox.showerror(title='Erro no Anexo', message=f'Não foi possível anexar o arquivo: {e}', parent=window) # 
        return # 

    try:
        # Configurações do servidor SMTP (exemplo para Gmail)
        smtp_server = 'smtp.gmail.com' # 
        smtp_port = 587 # 
        # Adaptação para outros provedores populares (exemplo)
        if "yahoo.com" in selected_domain.lower(): # 
             smtp_server = 'smtp.mail.yahoo.com' # 
        elif "hotmail.com" in selected_domain.lower() or "outlook.com" in selected_domain.lower(): # 
              smtp_server = 'smtp.office365.com' # 


        server = smtplib.SMTP(smtp_server, smtp_port) # 
        server.starttls() # 
        server.login(from_email, password) # 
        text = msg.as_string() # 
        server.sendmail(from_email, full_recipient_email, text) # 
        server.quit() # 
        messagebox.showinfo(title='Sucesso', message=f'Relatório de presença enviado para {full_recipient_email}.', parent=window) # 
    except smtplib.SMTPAuthenticationError: # 
        messagebox.showerror(title='Erro de E-mail', message='Erro de Autenticação SMTP. Verifique seu e-mail/senha e ' # 
                                                           'certifique-se de que "acesso a app menos seguro" está habilitado se estiver usando Gmail com senha normal (ou use uma Senha de App).', parent=window) # 
    except Exception as e: # 
        print(f"Falha no envio do e-mail: {e}") # 
        messagebox.showerror(title='Erro de E-mail', message=f'Falha ao enviar e-mail: {e}.\n' # 
                                                           'Verifique sua conexão com a internet e configurações de e-mail.', parent=window) # 

# --------------------------------------------

def delete_registration_csv_action(): # 
    global window
    if os.path.exists(STUDENT_DETAILS_CSV): # 
        if messagebox.askyesno("Confirmar Exclusão", # 
                               f"Tem certeza que deseja excluir TODOS os registros de estudantes ({os.path.basename(STUDENT_DETAILS_CSV)})?\n" # 
                               "Isso também tornará o arquivo de treinamento (Trainner.yml) inútil.", # 
                               parent=window):
            try:
                os.remove(STUDENT_DETAILS_CSV) # 
                messagebox.showinfo("Sucesso", "Arquivo de registros de estudantes excluído.", parent=window) # 
                update_registration_count_display() # 
                if os.path.exists(TRAINER_FILE): # 
                    if messagebox.askyesno("Ação Adicional", "Deseja excluir também o arquivo de treinamento (Trainner.yml)?", parent=window): # 
                        os.remove(TRAINER_FILE) # 
                        messagebox.showinfo("Sucesso", "Arquivo de treinamento (Trainner.yml) excluído.", parent=window) # 

            except Exception as e: # 
                messagebox.showerror("Erro", f"Não foi possível excluir o arquivo: {e}", parent=window) # 
    else: # 
        messagebox.showinfo("Aviso", "Arquivo de registros de estudantes não encontrado.", parent=window) # 

def delete_today_attendance_csv_action(): # 
    global window
    current_date_filename_part = datetime.datetime.now().strftime('%d-%m-%Y') # 
    file_path = os.path.join(ATTENDANCE_DIR, f"Attendance_{current_date_filename_part}.csv") # 

    if os.path.exists(file_path): # 
        if messagebox.askyesno("Confirmar Exclusão", # 
                               f"Tem certeza que deseja excluir o arquivo de presença de hoje ({os.path.basename(file_path)})?", # 
                               parent=window):
            try:
                os.remove(file_path) # 
                messagebox.showinfo("Sucesso", "Arquivo de presença de hoje excluído.", parent=window) # 
                populate_treeview_from_csv() # 
            except Exception as e: # 
                messagebox.showerror("Erro", f"Não foi possível excluir o arquivo: {e}", parent=window) # 
    else: # 
        messagebox.showinfo("Aviso", "Arquivo de presença de hoje não encontrado.", parent=window) # 

def delete_all_registered_images_action(): # 
    global window
    if messagebox.askyesno("Confirmar Exclusão Drástica", # 
                           "TEM CERTEZA que deseja excluir TODAS as imagens de treinamento registradas?\n" # 
                           "Esta ação NÃO PODE ser desfeita e também excluirá o arquivo de treinamento (Trainner.yml).", # 
                           icon='warning', parent=window):
        count_deleted = 0 # 
        files_failed_count = 0 # ADICIONADO PARA CONTAR FALHAS 
        for filename in os.listdir(TRAINING_IMAGE_DIR): # 
            file_path = os.path.join(TRAINING_IMAGE_DIR, filename) # 
            try:
                if os.path.isfile(file_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg')): # 
                    os.remove(file_path) # 
                    count_deleted += 1 # 
            except Exception as e: # 
                files_failed_count +=1 # 
                print(f"Erro ao excluir {file_path}: {e}") # 

        if files_failed_count > 0 : # 
             messagebox.showwarning("Sucesso Parcial", f"Excluídas {count_deleted} imagens.\nFalha ao excluir {files_failed_count} imagens. Verifique o console.", parent=window) # 
        elif count_deleted > 0: # 
             messagebox.showinfo("Sucesso", f"Todas as {count_deleted} imagens de treinamento foram excluídas.", parent=window) # 
        else: # 
             messagebox.showinfo("Informação", "Nenhuma imagem encontrada na pasta TrainingImage para excluir.", parent=window) # 


        if os.path.exists(TRAINER_FILE): # 
            try:
                os.remove(TRAINER_FILE) # 
                print("Arquivo Trainner.yml excluído.") # 
                messagebox.showinfo("Sucesso", "Arquivo de treinamento (Trainner.yml) também foi excluído.", parent=window) # 
            except Exception as e: # 
                print(f"Erro ao excluir Trainner.yml: {e}") # 
                messagebox.showerror("Erro", f"Não foi possível excluir Trainner.yml: {e}", parent=window) # 

        messagebox.showwarning("Aviso Adicional", # 
                               "As imagens e o treinamento foram excluídos.\n" # 
                               "Considere excluir também o arquivo de registros de estudantes (StudentDetails.csv) para consistência.", # 
                               parent=window)
    elif not os.path.exists(TRAINING_IMAGE_DIR): # Verificação se a pasta existe 
        messagebox.showinfo("Erro", "Pasta TrainingImage não encontrada.") # 


######################################## GUI FRONT-END SETUP ###########################################
def setup_gui():
    global window, clock_label, id_entry, name_entry, registration_status_label, \
           total_registrations_label, attendance_treeview, \
           recipient_email_entry, domain_var # Adiciona as globais do email para a GUI

    window = tk.Tk() # 
    window.geometry("1280x720") # 
    window.resizable(False, False) # 
    window.title("Sistema de Monitoramento de Presença por Reconhecimento Facial") # 
    window.configure(background='#2d420a') # 

    try:
        bg_image_path = os.path.join(BASE_DIR, "background_image1.png") # 
        if os.path.exists(bg_image_path): # 
            bg_image = Image.open(bg_image_path) # 
            bg_photo = ImageTk.PhotoImage(bg_image) # 
            background_label = tk.Label(window, image=bg_photo) # 
            background_label.image = bg_photo # 
            background_label.place(x=0, y=0, relwidth=1, relheight=1) # 
        else: # 
            print("Aviso: Imagem de fundo 'background_image1.png' não encontrada. Usando cor sólida.") # 
    except Exception as e: # 
        print(f"Erro ao carregar imagem de fundo: {e}") # 

    frame_attendance_actions = tk.Frame(window, bg="#c79cff") # 
    frame_attendance_actions.place(relx=0.05, rely=0.17, relwidth=0.43, relheight=0.80) # 
    frame_registration = tk.Frame(window, bg="#c79cff") # 
    frame_registration.place(relx=0.52, rely=0.17, relwidth=0.43, relheight=0.80) # 

    title_label = tk.Label(window, text="Sistema de Monitoramento de Presença Facial", # 
                           fg="white", bg="#2d420a", width=55, height=1, font=('sans-serif', 29, 'bold'))
    title_label.place(x=10, y=10) # 

    top_info_frame = tk.Frame(window, bg="#2d420a") # 
    top_info_frame.place(relx=0.0, rely=0.10, relwidth=1.0, height=40) # 

    ts_now = time.time() # 
    date_str_display = datetime.datetime.fromtimestamp(ts_now).strftime('%d-%B-%Y') # 
    date_label = tk.Label(top_info_frame, text=date_str_display, fg="#ff61e5", bg="green", # 
                          width=25, font=('sans-serif', 15, 'bold'))
    date_label.place(relx=0.4, rely=0.5, anchor="center") # 

    clock_label = tk.Label(top_info_frame, fg="#ff61e5", bg="green", width=15, font=('sans-serif', 15, 'bold')) # 
    clock_label.place(relx=0.6, rely=0.5, anchor="center") # 
    tick() # 

    tk.Label(frame_registration, text="Para Novos Registros", fg="black", bg="#00fcca", # 
             font=('sans-serif', 17, 'bold'), anchor='w').pack(side="top", fill="x", pady=(0,5)) # 
    tk.Label(frame_registration, text="ID do Estudante (Numérico):", width=25, height=1, fg="black", # 
             bg="#c79cff", font=('sans-serif', 15, 'bold')).pack(pady=(20,0)) # 
    id_entry = tk.Entry(frame_registration, width=32, fg="black", font=('sans-serif', 15, 'bold'), relief='solid') # 
    id_entry.pack(pady=(5,0)) # 
    tk.Label(frame_registration, text="Nome do Estudante:", width=20, fg="black", bg="#c79cff", # 
             font=('sans-serif', 15, 'bold')).pack(pady=(10,0))
    name_entry = tk.Entry(frame_registration, width=32, fg="black", font=('sans-serif', 15, 'bold'), relief='solid') # 
    name_entry.pack(pady=(5,0)) # 
    registration_status_label = tk.Label(frame_registration, text="1) Capture Imagens  >>>  2) Salve Perfil", # 
                                         bg="#c79cff", fg="black", width=39, height=1, # 
                                         font=('sans-serif', 14, 'bold')) # 
    registration_status_label.pack(pady=(20,0)) # 
    reg_button_frame = tk.Frame(frame_registration, bg="#c79cff") # 
    reg_button_frame.pack(side="top", pady=20, fill='x', padx=30) # 
    tk.Button(reg_button_frame, text="Capturar Imagens", command=take_images_action, fg="white", bg="#6d00fc", # 
              width=15, height=1, activebackground="white", font=('sans-serif', 15, 'bold')).pack(side=tk.LEFT, expand=True, padx=5) # 
    tk.Button(reg_button_frame, text="Salvar Perfil", command=prompt_password_for_profile_save, fg="white", bg="#6d00fc", # 
              width=15, height=1, activebackground="white", font=('sans-serif', 15, 'bold')).pack(side=tk.LEFT, expand=True, padx=5) # 
    clear_button_frame = tk.Frame(frame_registration, bg="#c79cff") # 
    clear_button_frame.pack(side="top", pady=5, fill='x', padx=30) # 
    tk.Button(clear_button_frame, text="Limpar ID", command=clear_id_entry, fg="black", bg="#ff7221", # 
              width=10, height=1, font=('sans-serif', 15, 'bold')).pack(side=tk.LEFT, expand=True, padx=5) # 
    tk.Button(clear_button_frame, text="Limpar Nome", command=clear_name_entry, fg="black", bg="#ff7221", # 
              width=10, height=1, font=('sans-serif', 15, 'bold')).pack(side=tk.LEFT, expand=True, padx=5) # 
    total_registrations_label = tk.Label(frame_registration, text="", bg="#c79cff", fg="black", # 
                                         width=39, height=1, font=('sans-serif', 16, 'bold'))
    total_registrations_label.pack(pady=(10,0), side="bottom") # 
    update_registration_count_display() # 
    tk.Button(frame_registration, text="Contato", command=contact, fg="black", bg="lightblue", # 
              width=20, height=1, font=('sans-serif', 10, 'bold')).pack(side="bottom", pady=5)
    tk.Button(frame_registration, text="Alterar Senha Admin", command=open_change_password_window, fg="black", bg="lightgrey", # 
              width=20, height=1, font=('sans-serif', 10, 'bold')).pack(side="bottom", pady=10)

    tk.Label(frame_attendance_actions, text="Presença Diária e Ações", fg="black", bg="#00fcca", # 
             font=('sans-serif', 17, 'bold'), anchor='w').pack(side="top", fill="x", pady=(0,5)) # 

    # --- SEÇÃO DE EMAIL NA GUI ---
    email_frame = tk.Frame(frame_attendance_actions, bg="#DDDDDD") # Cor de fundo um pouco diferente para destacar 
    email_frame.pack(side="top", fill="x", pady=5, padx=5) # 

    tk.Label(email_frame, text="E-mail Destinatário:", width=16, fg="black", bg="#DDDDDD", font=('sans-serif', 9, 'bold'), anchor='w').grid(row=0, column=0, padx=2, pady=2, sticky='w') # 
    recipient_email_entry = tk.Entry(email_frame, width=20, fg="black", bg="white", font=('sans-serif', 10, 'bold')) # 
    recipient_email_entry.grid(row=0, column=1, padx=0, pady=2, sticky='ew') # 

    tk.Label(email_frame, text="@", width=1, fg="black", bg="#DDDDDD", font=('sans-serif', 10, 'bold')).grid(row=0, column=2, padx=0, pady=2) # 

    email_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"] # 
    domain_var = tk.StringVar(email_frame) # 
    domain_var.set(email_domains[0]) # 
    domain_dropdown = tk.OptionMenu(email_frame, domain_var, *email_domains) # 
    domain_dropdown.config(width=12, font=('sans-serif', 9, 'bold'), relief='raised') # 
    domain_dropdown.grid(row=0, column=3, padx=2, pady=2, sticky='ew') # 

    send_email_button = tk.Button(email_frame, text="Enviar Relatório", command=send_email, fg="white", bg="#007bff", width=12, font=('sans-serif', 9, 'bold')) # CHAMANDO A FUNÇÃO send_email COMPLETA 
    send_email_button.grid(row=0, column=4, padx=(5,2), pady=2, sticky='e') # 
    email_frame.grid_columnconfigure(1, weight=1) # 
    email_frame.grid_columnconfigure(3, weight=1) # 
    # ---------------------------------

    delete_buttons_frame = tk.Frame(frame_attendance_actions, bg="#c79cff") # 
    delete_buttons_frame.pack(side="top", fill="x", pady=5, padx=5) # 
    btn_del_reg = tk.Button(delete_buttons_frame, text="Excluir Registros CSV", command=delete_registration_csv_action, # 
                           fg="white", bg="red", width=18, font=('sans-serif', 8, 'bold'))
    btn_del_reg.pack(side=tk.LEFT, padx=2, expand=True, fill='x') # 
    btn_del_att = tk.Button(delete_buttons_frame, text="Excluir Presença CSV (Hoje)", command=delete_today_attendance_csv_action, # 
                           fg="white", bg="red", width=18, font=('sans-serif', 8, 'bold'))
    btn_del_att.pack(side=tk.LEFT, padx=2, expand=True, fill='x') # 
    btn_del_img = tk.Button(delete_buttons_frame, text="Excluir Imagens Registradas", command=delete_all_registered_images_action, # 
                           fg="white", bg="red", width=18, font=('sans-serif', 8, 'bold'))
    btn_del_img.pack(side=tk.LEFT, padx=2, expand=True, fill='x') # 
    attendance_action_frame = tk.Frame(frame_attendance_actions, bg="#c79cff") # 
    attendance_action_frame.pack(side="top", fill="x", pady=10, padx=5) # 
    tk.Label(attendance_action_frame, text="Presença Diária:", width=15, fg="black", bg="#c79cff", # 
             height=1, font=('sans-serif', 15, 'bold')).pack(side=tk.LEFT, padx=(0,10))
    tk.Button(attendance_action_frame, text="Registrar Presença", command=track_images_action, fg="black", # 
              bg="#3ffc00", width=15, height=1, activebackground="white", # 
              font=('sans-serif', 12, 'bold')).pack(side=tk.LEFT, expand=True, fill='x') # 
    tree_frame = tk.Frame(frame_attendance_actions) # 
    tree_frame.pack(side="top", fill="both", expand=True, pady=5, padx=5) # 

    tv_columns = ('name', 'date', 'time') # 
    attendance_treeview = ttk.Treeview(tree_frame, height=10, columns=tv_columns, style="Custom.Treeview") # 
    style = ttk.Style() # 
    style.configure("Custom.Treeview", font=('sans-serif', 10)) # 
    style.configure("Custom.Treeview.Heading", font=('sans-serif', 11, 'bold')) # 

    attendance_treeview.column('#0', width=80, anchor='w', minwidth=60) # 
    attendance_treeview.column('name', width=150, anchor='w', minwidth=100) # 
    attendance_treeview.column('date', width=100, anchor='center', minwidth=80) # 
    attendance_treeview.column('time', width=100, anchor='center', minwidth=80) # 
    attendance_treeview.heading('#0', text='ID Reg.') # 
    attendance_treeview.heading('name', text='NOME') # 
    attendance_treeview.heading('date', text='DATA') # 
    attendance_treeview.heading('time', text='HORA') # 
    yscroll = ttk.Scrollbar(tree_frame, orient='vertical', command=attendance_treeview.yview) # 
    xscroll = ttk.Scrollbar(tree_frame, orient='horizontal', command=attendance_treeview.xview) # 
    attendance_treeview.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set) # 
    yscroll.pack(side='right', fill='y') # 
    xscroll.pack(side='bottom', fill='x') # 
    attendance_treeview.pack(side='left', fill='both', expand=True) # 

    populate_treeview_from_csv() # 

    tk.Button(frame_attendance_actions, text="Sair do Sistema", command=window.destroy, fg="white", bg="#eb4600", # 
              width=35, height=1, activebackground="white", font=('sans-serif', 15, 'bold')).pack(side="bottom", fill="x", pady=10, padx=5) # 

    # --- MENUBAR (COMO ESTAVA NO SEU ARQUIVO .TXT) ---
    menubar = tk.Menu(window, relief='ridge') # 
    filemenu = tk.Menu(menubar, tearoff=0) # 
    filemenu.add_command(label='Change Password', command=open_change_password_window) # Alterado para chamar a função correta 
    filemenu.add_command(label='Contact Us', command=contact) # 
    filemenu.add_separator() # 
    filemenu.add_command(label='Exit', command=window.destroy) # 
    menubar.add_cascade(label='Help', font=('comic', 12, ' normal '), menu=filemenu) # 
    window.configure(menu=menubar) # 
    # ---------------------------------------------

    window.mainloop()

############################################# MAIN EXECUTION ###########################################
if __name__ == "__main__":
    assure_path_exists(TRAINING_IMAGE_LABEL_DIR)
    assure_path_exists(STUDENT_DETAILS_DIR)
    assure_path_exists(TRAINING_IMAGE_DIR)
    assure_path_exists(ATTENDANCE_DIR)

    setup_gui()