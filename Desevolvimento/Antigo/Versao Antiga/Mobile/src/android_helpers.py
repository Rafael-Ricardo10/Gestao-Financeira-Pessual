def authenticate_with_biometrics(title, message, callback):
    """
    Implementa autenticação biométrica no Android

    Args:
        title: Título da solicitação
        message: Mensagem para o usuário
        callback: Função chamada após autenticação (recebe True/False)
    """
    try:
        # Importar bibliotecas específicas do Android
        from rubicon.java import JavaClass, JavaInterface

        # Interface para receber callbacks do Android
        class AuthenticationCallback(JavaInterface('androidx/biometric/BiometricPrompt$AuthenticationCallback')):
            def __init__(self, callback_fn):
                super().__init__()
                self.callback_fn = callback_fn

            def onAuthenticationSucceeded(self, result):
                self.callback_fn(True)

            def onAuthenticationFailed(self):
                self.callback_fn(False)

            def onAuthenticationError(self, errorCode, errString):
                self.callback_fn(False)

        # Importar classes do Android
        BiometricPrompt = JavaClass('androidx/biometric/BiometricPrompt')
        Executor = JavaClass('java/util/concurrent/Executor')
        MainActivity = JavaClass('org/beeware/android/MainActivity')

        # Obter activity atual
        activity = MainActivity.singletonThis

        # Criar executor
        executor = JavaClass('java/util/concurrent/Executors').newSingleThreadExecutor()

        # Configurar callback
        auth_callback = AuthenticationCallback(callback)

        # Configurar e mostrar prompt biométrico
        prompt_info = BiometricPrompt.PromptInfo.Builder() \
            .setTitle(title) \
            .setSubtitle(message) \
            .setNegativeButtonText("Cancelar") \
            .build()

        biometric_prompt = BiometricPrompt(activity, executor, auth_callback)
        biometric_prompt.authenticate(prompt_info)

    except Exception as e:
        print(f"Erro na autenticação biométrica: {e}")
        callback(False)

def select_database_directory(app, callback):
    """
    Permite selecionar diretório do banco de dados no Android

    Args:
        app: Instância do aplicativo
        callback: Função chamada após seleção (recebe o caminho)
    """
    try:
        # No Android, vamos usar o SAF (Storage Access Framework)
        from rubicon.java import JavaClass

        Intent = JavaClass('android/content/Intent')
        MainActivity = JavaClass('org/beeware/android/MainActivity')

        # Cria intent para seleção de diretório
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)

        # Armazena callback para uso posterior
        app.store_value('dir_select_callback', callback)

        # Inicia a activity com o intent
        MainActivity.singletonThis.startActivityForResult(intent, 42)

        # O callback será chamado pelo código nativo do Android
        # através da implementação do BeeWare

    except Exception as e:
        print(f"Erro ao selecionar diretório: {e}")
        callback(None)
