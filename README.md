Sistema de controle de presença baseado em reconhecimento facial
Um sistema de controle de presença com interface gráfica (GUI) em Python que utiliza reconhecimento facial para registrar a frequência.

Neste projeto em Python, desenvolvi um sistema de controle de presença que registra a frequência por meio da técnica de reconhecimento facial. Integrei-o também com uma GUI (Interface Gráfica do Usuário) para facilitar sua utilização por qualquer pessoa. A GUI para este projeto também foi desenvolvida em Python utilizando a biblioteca Tkinter.

TECNOLOGIAS UTILIZADAS:

Tkinter: para toda a GUI.
OpenCV: para captura de imagens e reconhecimento facial ( cv2.face.LBPHFaceRecognizer_create() ).
CSV, Numpy, Pandas, datetime, etc.: para outras finalidades.
FUNCIONALIDADES:

Fácil de usar com suporte de GUI interativa.
Proteção por senha para o registro de novas pessoas.
Cria/Atualiza um arquivo CSV com os detalhes dos estudantes no momento do registro.
Cria um novo arquivo CSV diariamente para o controle de presença e registra a frequência com data e hora exatas.
Exibe atualizações da frequência do dia em tempo real na tela principal em formato de tabela, contendo Id, nome, data e hora.