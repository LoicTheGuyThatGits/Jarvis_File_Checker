; JarvisSetup.exe: installs Jarvis for the current Windows user (no administrator rights needed).
; Built by .github/workflows/release.yml with Inno Setup 6:  iscc /DMyAppVersion=2026.11.26 installer\jarvis.iss
; It copies the program into %LOCALAPPDATA%\Programs\Jarvis, adds Start menu (and desktop) shortcuts and an entry in
; Windows' installed apps, then runs tools\setup-jarvis.ps1 for Python and the packages. Updates afterwards come from the
; newest release, from inside Jarvis (Settings > Jarvis & updates). Uninstalling keeps your data unless you ask.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyRepo "https://github.com/LoicTheGuyThatGits/Jarvis_File_Checker"

[Setup]
AppId={{7C3E2A91-5B4D-4F0E-9A62-1D8B3C7E4F25}
AppName=Jarvis
AppVersion={#MyAppVersion}
AppVerName=Jarvis {#MyAppVersion}
AppPublisher=Jarvis
AppPublisherURL={#MyRepo}
AppSupportURL={#MyRepo}/issues
AppUpdatesURL={#MyRepo}/releases
DefaultDirName={localappdata}\Programs\Jarvis
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=JarvisSetup-{#MyAppVersion}
SetupIconFile=..\web\icons\jarvis.ico
UninstallDisplayIcon={app}\web\icons\jarvis.ico
UninstallDisplayName=Jarvis
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
CloseApplications=no
LicenseFile=..\LICENSE

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "he"; MessagesFile: "compiler:Languages\Hebrew.isl"

[CustomMessages]
en.Needs=Jarvis runs on Python. If Python 3.10 to 3.13 is not on this PC, setup installs Python 3.12 for your Windows user (free, from winget or python.org) and accepts its licence for you. The packages Jarvis uses are downloaded into the Jarvis folder. This needs an internet connection and takes a few minutes.
fr.Needs=Jarvis fonctionne avec Python. Si Python 3.10 à 3.13 n'est pas sur ce PC, l'installation installe Python 3.12 pour votre utilisateur Windows (gratuit, depuis winget ou python.org) et accepte sa licence pour vous. Les paquets utilisés par Jarvis sont téléchargés dans le dossier de Jarvis. Il faut une connexion internet, et cela prend quelques minutes.
de.Needs=Jarvis läuft mit Python. Fehlt Python 3.10 bis 3.13 auf diesem PC, installiert das Setup Python 3.12 für Ihr Windows-Benutzerkonto (kostenlos, über winget oder python.org) und akzeptiert dessen Lizenz für Sie. Die Pakete, die Jarvis nutzt, werden in den Jarvis-Ordner geladen. Dafür ist eine Internetverbindung nötig; es dauert einige Minuten.
it.Needs=Jarvis funziona con Python. Se su questo PC non c'è Python da 3.10 a 3.13, l'installazione installa Python 3.12 per il tuo utente Windows (gratuito, da winget o python.org) e ne accetta la licenza per te. I pacchetti usati da Jarvis vengono scaricati nella cartella di Jarvis. Serve una connessione internet e ci vogliono alcuni minuti.
es.Needs=Jarvis funciona con Python. Si este PC no tiene Python 3.10 a 3.13, la instalación instala Python 3.12 para tu usuario de Windows (gratis, desde winget o python.org) y acepta su licencia por ti. Los paquetes que usa Jarvis se descargan en la carpeta de Jarvis. Hace falta conexión a internet y tarda unos minutos.
pt.Needs=O Jarvis funciona com Python. Se este PC não tiver Python 3.10 a 3.13, a instalação instala o Python 3.12 para o seu usuário do Windows (grátis, pelo winget ou python.org) e aceita a licença dele por você. Os pacotes que o Jarvis usa são baixados na pasta do Jarvis. Precisa de internet e leva alguns minutos.
nl.Needs=Jarvis werkt met Python. Staat Python 3.10 tot 3.13 niet op deze pc, dan installeert de setup Python 3.12 voor je Windows-gebruiker (gratis, via winget of python.org) en accepteert de licentie voor je. De pakketten die Jarvis gebruikt worden in de Jarvis-map gedownload. Dit heeft internet nodig en duurt een paar minuten.
pl.Needs=Jarvis działa na Pythonie. Jeśli na tym komputerze nie ma Pythona od 3.10 do 3.13, instalator zainstaluje Pythona 3.12 dla Twojego użytkownika Windows (za darmo, z winget lub python.org) i zaakceptuje za Ciebie jego licencję. Pakiety, których używa Jarvis, zostaną pobrane do folderu Jarvisa. Potrzebne jest połączenie z internetem; trwa to kilka minut.
ja.Needs=Jarvis は Python で動きます。この PC に Python 3.10 から 3.13 がない場合、セットアップがこの Windows ユーザー用に Python 3.12 をインストールし（無料、winget または python.org から）、そのライセンスに代わりに同意します。Jarvis が使うパッケージは Jarvis のフォルダーにダウンロードされます。インターネット接続が必要で、数分かかります。
he.Needs=Jarvis רץ על Python. אם אין במחשב Python בגרסאות 3.10 עד 3.13, ההתקנה תתקין Python 3.12 עבור משתמש ה-Windows שלך (בחינם, דרך winget או python.org) ותאשר את הרישיון שלו בשמך. החבילות ש-Jarvis משתמש בהן יורדות לתיקייה של Jarvis. נדרש חיבור לאינטרנט, וזה לוקח כמה דקות.
en.Autostart=Start Jarvis when Windows starts (in the tray)
fr.Autostart=Démarrer Jarvis avec Windows (dans la zone de notification)
de.Autostart=Jarvis mit Windows starten (im Infobereich)
it.Autostart=Avvia Jarvis all'avvio di Windows (nell'area di notifica)
es.Autostart=Iniciar Jarvis con Windows (en la bandeja)
pt.Autostart=Iniciar o Jarvis com o Windows (na bandeja)
nl.Autostart=Jarvis starten met Windows (in het systeemvak)
pl.Autostart=Uruchamiaj Jarvisa razem z Windows (w zasobniku)
ja.Autostart=Windows の起動時に Jarvis を開始する（通知領域）
he.Autostart=הפעלת Jarvis עם הפעלת Windows (במגש המערכת)
en.Voice=Speech recognition for "Hey Jarvis" and dictation (about 150 MB more)
fr.Voice=Reconnaissance vocale pour « Hey Jarvis » et la dictée (environ 150 Mo de plus)
de.Voice=Spracherkennung für „Hey Jarvis“ und Diktat (etwa 150 MB mehr)
it.Voice=Riconoscimento vocale per «Hey Jarvis» e la dettatura (circa 150 MB in più)
es.Voice=Reconocimiento de voz para «Hey Jarvis» y el dictado (unos 150 MB más)
pt.Voice=Reconhecimento de voz para “Hey Jarvis” e ditado (cerca de 150 MB a mais)
nl.Voice=Spraakherkenning voor “Hey Jarvis” en dicteren (ongeveer 150 MB extra)
pl.Voice=Rozpoznawanie mowy dla „Hey Jarvis” i dyktowania (około 150 MB więcej)
ja.Voice=「Hey Jarvis」と音声入力のための音声認識（約 150 MB 追加）
he.Voice=זיהוי דיבור עבור “Hey Jarvis” והכתבה (בערך 150 MB נוספים)
en.Repair=Repair Jarvis
fr.Repair=Réparer Jarvis
de.Repair=Jarvis reparieren
it.Repair=Ripara Jarvis
es.Repair=Reparar Jarvis
pt.Repair=Reparar o Jarvis
nl.Repair=Jarvis herstellen
pl.Repair=Napraw Jarvisa
ja.Repair=Jarvis を修復
he.Repair=תיקון Jarvis
en.Working=Installing Python and the packages Jarvis uses (a few minutes)...
fr.Working=Installation de Python et des paquets utilisés par Jarvis (quelques minutes)...
de.Working=Python und die Pakete für Jarvis werden installiert (einige Minuten)...
it.Working=Installazione di Python e dei pacchetti usati da Jarvis (alcuni minuti)...
es.Working=Instalando Python y los paquetes que usa Jarvis (unos minutos)...
pt.Working=Instalando o Python e os pacotes que o Jarvis usa (alguns minutos)...
nl.Working=Python en de pakketten voor Jarvis worden geïnstalleerd (een paar minuten)...
pl.Working=Instaluję Pythona i pakiety używane przez Jarvisa (kilka minut)...
ja.Working=Python と Jarvis が使うパッケージをインストールしています（数分）...
he.Working=מתקין את Python ואת החבילות ש-Jarvis משתמש בהן (כמה דקות)...
en.Failed=Jarvis was copied, but setting up Python and its packages did not finish (code %1). The details are in data\install.log in the Jarvis folder. Check the internet connection, then open "Repair Jarvis" from the Start menu.
fr.Failed=Jarvis a été copié, mais l'installation de Python et de ses paquets n'a pas abouti (code %1). Les détails sont dans data\install.log dans le dossier de Jarvis. Vérifiez la connexion internet, puis ouvrez « Réparer Jarvis » depuis le menu Démarrer.
de.Failed=Jarvis wurde kopiert, aber die Einrichtung von Python und seinen Paketen wurde nicht fertig (Code %1). Details stehen in data\install.log im Jarvis-Ordner. Prüfen Sie die Internetverbindung und öffnen Sie dann „Jarvis reparieren“ im Startmenü.
it.Failed=Jarvis è stato copiato, ma la configurazione di Python e dei suoi pacchetti non è terminata (codice %1). I dettagli sono in data\install.log nella cartella di Jarvis. Controlla la connessione internet, poi apri «Ripara Jarvis» dal menu Start.
es.Failed=Jarvis se ha copiado, pero la instalación de Python y sus paquetes no terminó (código %1). Los detalles están en data\install.log en la carpeta de Jarvis. Comprueba la conexión a internet y abre «Reparar Jarvis» desde el menú Inicio.
pt.Failed=O Jarvis foi copiado, mas a instalação do Python e dos pacotes não terminou (código %1). Os detalhes estão em data\install.log na pasta do Jarvis. Verifique a internet e abra “Reparar o Jarvis” no menu Iniciar.
nl.Failed=Jarvis is gekopieerd, maar het instellen van Python en de pakketten is niet afgerond (code %1). Details staan in data\install.log in de Jarvis-map. Controleer de internetverbinding en open daarna “Jarvis herstellen” in het Startmenu.
pl.Failed=Jarvis został skopiowany, ale instalacja Pythona i pakietów nie została ukończona (kod %1). Szczegóły są w pliku data\install.log w folderze Jarvisa. Sprawdź połączenie z internetem, a potem otwórz „Napraw Jarvisa” z menu Start.
ja.Failed=Jarvis はコピーされましたが、Python とパッケージのセットアップが完了しませんでした（コード %1）。詳細は Jarvis フォルダーの data\install.log にあります。インターネット接続を確認してから、スタートメニューの「Jarvis を修復」を開いてください。
he.Failed=Jarvis הועתק, אבל ההתקנה של Python והחבילות שלו לא הסתיימה (קוד %1). הפרטים נמצאים ב-data\install.log בתיקיית Jarvis. בדקו את החיבור לאינטרנט, ואז פתחו את “תיקון Jarvis” מתפריט התחל.
en.KeepData=Also delete your Jarvis data (settings, chats, memory, notes)?%n%nChoose No to keep it for a later install.
fr.KeepData=Supprimer aussi vos données Jarvis (réglages, conversations, mémoire, notes) ?%n%nChoisissez Non pour les garder pour une prochaine installation.
de.KeepData=Auch Ihre Jarvis-Daten löschen (Einstellungen, Chats, Gedächtnis, Notizen)?%n%nWählen Sie Nein, um sie für eine spätere Installation zu behalten.
it.KeepData=Eliminare anche i tuoi dati di Jarvis (impostazioni, chat, memoria, note)?%n%nScegli No per conservarli per un'installazione futura.
es.KeepData=¿Borrar también tus datos de Jarvis (ajustes, chats, memoria, notas)?%n%nElige No para conservarlos para una instalación futura.
pt.KeepData=Apagar também os seus dados do Jarvis (configurações, chats, memória, notas)?%n%nEscolha Não para guardá-los para uma instalação futura.
nl.KeepData=Ook je Jarvis-gegevens verwijderen (instellingen, chats, geheugen, notities)?%n%nKies Nee om ze te bewaren voor een latere installatie.
pl.KeepData=Usunąć też Twoje dane Jarvisa (ustawienia, czaty, pamięć, notatki)?%n%nWybierz Nie, aby zachować je na później.
ja.KeepData=Jarvis のデータ（設定、チャット、記憶、メモ）も削除しますか？%n%n後で再インストールするときのために残すには「いいえ」を選んでください。
he.KeepData=למחוק גם את נתוני Jarvis שלך (הגדרות, שיחות, זיכרון, פתקים)?%n%nבחרו "לא" כדי לשמור אותם להתקנה מאוחרת יותר.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:Autostart}"; Flags: unchecked
Name: "voice"; Description: "{cm:Voice}"

[Files]
Source: "..\app\*"; DestDir: "{app}\app"; Excludes: "__pycache__,*.pyc"; Flags: recursesubdirs ignoreversion
Source: "..\web\*"; DestDir: "{app}\web"; Flags: recursesubdirs ignoreversion
Source: "..\tools\*"; DestDir: "{app}\tools"; Excludes: "__pycache__,*.pyc"; Flags: recursesubdirs ignoreversion
Source: "..\*.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\filecheck.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\manifest.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{autoprograms}\Jarvis"; Filename: "{app}\start-jarvis-app.bat"; WorkingDir: "{app}"; IconFilename: "{app}\web\icons\jarvis.ico"; Flags: runminimized
Name: "{autoprograms}\{cm:Repair}"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\setup-jarvis.ps1"" -Root ""{app}"" -Voice"; WorkingDir: "{app}"; IconFilename: "{app}\web\icons\jarvis.ico"
Name: "{autodesktop}\Jarvis"; Filename: "{app}\start-jarvis-app.bat"; WorkingDir: "{app}"; IconFilename: "{app}\web\icons\jarvis.ico"; Flags: runminimized; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Jarvis"; ValueData: "cmd /c start """" /min ""{app}\start-jarvis-app.bat"" hidden"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\start-jarvis-app.bat"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Jarvis}"; Flags: postinstall nowait skipifsilent runminimized

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\app\__pycache__"
Type: filesandordirs; Name: "{app}\tools\__pycache__"

[Code]
var
  NeedsPage: TOutputMsgWizardPage;

procedure InitializeWizard();
begin
  NeedsPage := CreateOutputMsgPage(wpSelectTasks, 'Python', '', CustomMessage('Needs'));
end;

{ A running Jarvis would keep its files in use: stop the copies that run from this folder. }
procedure StopJarvis();
var
  Code: Integer;
  Dir: String;
begin
  Dir := ExpandConstant('{app}');
  StringChangeEx(Dir, '''', '''''', True);
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like ''python*'' -and $_.CommandLine -like ''*' + Dir + '*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"',
       '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if DirExists(ExpandConstant('{app}')) then
    StopJarvis();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Params: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := CustomMessage('Working');
    Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\setup-jarvis.ps1') + '" -Root "' + ExpandConstant('{app}') +
              '" -Version "{#MyAppVersion}" -Releases';
    if WizardIsTaskSelected('voice') then
      Params := Params + ' -Voice';
    if not Exec('powershell.exe', Params, ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, Code) or (Code <> 0) then
      SuppressibleMsgBox(FmtMessage(CustomMessage('Failed'), [IntToStr(Code)]), mbError, MB_OK, IDOK);
  end;
end;

function InitializeUninstall(): Boolean;
begin
  StopJarvis();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{app}\data')) then
    if SuppressibleMsgBox(CustomMessage('KeepData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(ExpandConstant('{app}\data'), True, True, True);
end;
