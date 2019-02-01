# -*- mode: python -*-

import os

block_cipher = None

exe_full_path = os.path.abspath('.')
print("Running in directory " + exe_full_path)

a = Analysis(['server.py'],
             pathex=[exe_full_path],
             binaries=[],
             datas=[(exe_full_path + os.sep + 'templates','templates'),
             (exe_full_path + os.sep + 'static','static'),
			 (exe_full_path + os.sep + 'perf_events','perf_events'),
			 (exe_full_path + os.sep + 'src' + os.sep + 'StackCollapse.py','src'),
             (exe_full_path + os.sep + 'pygal' + os.sep + 'css','pygal' + os.sep + 'css'),
             (exe_full_path + os.sep + 'results','results')],
             hiddenimports=[
              'email.mime.multipart',
               'email.mime.message',
                'email.mime.image',
                 'email.mime.audio',
                  'email.mime.text'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='perf_analyzer',
          debug=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='server')
