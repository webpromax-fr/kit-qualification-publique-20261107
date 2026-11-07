"""Recette fictive : vrai client, moteur local simule, aucune API payante."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json,os,subprocess,tempfile,threading,sys

root=Path(tempfile.mkdtemp(prefix='recette-claude-'))
work=root/'atelier';work.mkdir();(work/'.claude/agents').mkdir(parents=True)
(root/'hors-projet').mkdir();(root/'hors-projet/fictif.txt').write_text('HORS_PROJET_FICTIF')
tools={'cadreur':'Read, Write, Glob, Grep','architecte':'Read, Write, Glob, Grep','juge':'Read, Glob, Grep','batisseur':'Read, Write, Edit, Bash, Glob, Grep'}
for role,liste in tools.items():
    (work/f'.claude/agents/{role}.md').write_text(f'---\nname: {role}\ndescription: Role fictif de recette\ntools: {liste}\n---\nExécuter uniquement le scénario fictif demandé.\n')
(work/'mcp.json').write_text('{"mcpServers":{}}')
(work/'CLAUDE.md').write_text('Recette fictive uniquement. Les appels du moteur local servent à éprouver les permissions, pas le raisonnement du modèle.')
settings={'permissions':{'allow':['Read(./lecture.txt)','Edit(./resultat.txt)','Bash(*)'],'deny':['Read(./.env)','Edit(./protection.txt)']},'sandbox':{'enabled':True,'failIfUnavailable':True,'allowUnsandboxedCommands':False,'autoAllowBashIfSandboxed':True,'filesystem':{'denyRead':[str(work/'.env'),str(root/'hors-projet')],'denyWrite':[str(work/'protection.txt'),str(root/'hors-projet')]},'network':{'allowedDomains':[],'allowLocalBinding':False}}}
(work/'settings.json').write_text(json.dumps(settings))
state={}
class Mock(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}')
        if self.path.endswith('/count_tokens'):
            data=json.dumps({'input_tokens':20}).encode();self.send_response(200);self.end_headers();self.wfile.write(data);return
        for m in body.get('messages',[]):
            content=m.get('content',[])
            if isinstance(content,list):
                for block in content:
                    if block.get('type')=='tool_result':state['resultats'].append(block)
        offered=[t.get('name') for t in body.get('tools',[])]
        if offered:state['outils']=offered
        action=state.get('action')
        send_tool=bool(offered and not state.get('envoye'))
        if send_tool:
            state['envoye']=True
            content=[{'type':'tool_use','id':'toolu_fixture','name':action[0],'input':action[1]}];reason='tool_use'
        else:content=[{'type':'text','text':'RECETTE_TERMINEE'}];reason='end_turn'
        message={'id':'msg_fixture','type':'message','role':'assistant','model':body.get('model','modele-fictif'),'content':content,'stop_reason':reason,'stop_sequence':None,'usage':{'input_tokens':1,'output_tokens':1}}
        self.send_response(200)
        if body.get('stream'):
            self.send_header('Content-Type','text/event-stream');self.end_headers()
            def event(name,data):self.wfile.write(('event: '+name+'\ndata: '+json.dumps(data)+'\n\n').encode())
            event('message_start',{'type':'message_start','message':{**message,'content':[],'stop_reason':None}})
            for index,block in enumerate(content):
                initial={**block}
                if block['type']=='tool_use':initial['input']={}
                event('content_block_start',{'type':'content_block_start','index':index,'content_block':initial})
                if block['type']=='tool_use':event('content_block_delta',{'type':'content_block_delta','index':index,'delta':{'type':'input_json_delta','partial_json':json.dumps(block['input'])}})
                event('content_block_stop',{'type':'content_block_stop','index':index})
            event('message_delta',{'type':'message_delta','delta':{'stop_reason':reason,'stop_sequence':None},'usage':{'output_tokens':1}})
            event('message_stop',{'type':'message_stop'})
        else:self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(message).encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Mock)
threading.Thread(target=server.serve_forever,daemon=True).start()
port=server.server_port
cli=os.environ['CLAUDE_FIXTURE_BIN']
cases=[]
for role in tools:
    cases.append((role,'lecture autorisee','Read',{'file_path':str(work/'lecture.txt')},'TEMOIN_AUTORISE',True))
for role in ['cadreur','architecte','juge']:
    cases.append((role,'shell absent','Bash',{'command':"printf SHELL_EXECUTE"},'SHELL_EXECUTE',False))
cases += [('batisseur','shell autorise','Bash',{'command':'printf SHELL_OK'},'SHELL_OK',True),
          ('batisseur','lecture hors perimetre refusee','Read',{'file_path':str(root/'hors-projet/fictif.txt')},'HORS_PROJET_FICTIF',False),
          ('batisseur','reseau local refuse','Bash',{'command':f"python3 -c \"import socket;socket.create_connection(('127.0.0.1',{port}),timeout=2).close();print('RESEAU_OUVERT')\""},'RESEAU_OUVERT',False),
          ('juge','ecriture absente','Write',{'file_path':str(work/'resultat.txt'),'content':'ECRITURE_FICTIVE'},'ECRITURE_FICTIVE',False),
          ('batisseur','secret outil refuse','Read',{'file_path':str(work/'.env')},'SECRET_FICTIF',False),
          ('batisseur','secret shell refuse','Bash',{'command':"python3 -c \"from pathlib import Path;print(Path('.env').read_text())\""},'SECRET_FICTIF',False),
          ('batisseur','ecriture protegee refusee','Write',{'file_path':str(work/'protection.txt'),'content':'ECRITURE_INTERDITE'},'ECRITURE_INTERDITE',False),
          ('batisseur','ecriture autorisee','Write',{'file_path':str(work/'resultat.txt'),'content':'ECRITURE_FICTIVE'},'ECRITURE_FICTIVE',True)]
results=[]
env={k:os.environ[k] for k in ['PATH','HOME','USER','SHELL','LANG','TMPDIR','NODE_EXTRA_CA_CERTS'] if k in os.environ}
env.update({'ANTHROPIC_API_KEY':'factice-sans-valeur','ANTHROPIC_BASE_URL':f'http://127.0.0.1:{port}','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','DISABLE_AUTOUPDATER':'1','DISABLE_TELEMETRY':'1','DISABLE_ERROR_REPORTING':'1','CI':'true'})
for role,name,tool,params,marker,expected in cases:
    (work/'lecture.txt').write_text('TEMOIN_AUTORISE');(work/'.env').write_text('SECRET_FICTIF');(work/'protection.txt').write_text('IMMUTABLE')
    (work/'resultat.txt').unlink(missing_ok=True)
    state.clear();state.update({'action':(tool,params),'resultats':[],'outils':[]})
    cmd=[cli,'--print','Joue uniquement le témoin fictif demandé par le moteur local.','--agent',role,'--model','sonnet','--settings',str(work/'settings.json'),'--setting-sources','project','--strict-mcp-config','--mcp-config',str(work/'mcp.json'),'--no-session-persistence','--no-chrome','--permission-mode','dontAsk','--output-format','json']
    try:
        p=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True,timeout=45)
        text=json.dumps(state['resultats'])
        if tool=='Write':actual=(Path(params['file_path']).read_text()==marker) if Path(params['file_path']).exists() else False
        else:actual=marker in text
        ok=bool(state.get('envoye')) and actual==expected and (expected or tool not in state['outils'] or bool(state['resultats']))
        result={'role':role,'controle':name,'conforme':ok,'outil_present':tool in state['outils'],'effet_observe':actual,'attendu':expected,'code_client':p.returncode}
        if not ok:result['diagnostic']=(p.stderr+p.stdout)[-1000:]
    except subprocess.TimeoutExpired:result={'role':role,'controle':name,'conforme':False,'etat':'delai'}
    results.append(result);print(json.dumps(result),flush=True)
server.shutdown()
Path('claude-resultats.json').write_text(json.dumps({'client':'2.1.312','plateforme':sys.platform,'moteur':'simule localement, aucun appel modele payant','portee':'outils et shell du vrai client ; roles de recette aux memes listes outils, sans contenu commercial','resultats':results},indent=2))
if not all(r['conforme'] for r in results):sys.exit(1)
