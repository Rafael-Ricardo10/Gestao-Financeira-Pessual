// ==================== ESTADO GLOBAL ====================
const E = {
    token: null, user: null, isAdmin: false, chaveSession: null,
    transacoes: [], categorias: [], todosNomesFantasia: [],
    paginaAtual: 'dashboard', transacaoEditando: null,
    categoriaEditando: null, nomesSelecionados: [],
    transMover: null, empAtual: null,
};

// ==================== UTILS ====================
function fmtMoeda(v){
    return 'R$ '+parseFloat(v||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
}
function fmtData(d){
    if(!d)return '-';
    const p=d.split('-');
    return p.length===3?p[2]+'/'+p[1]+'/'+p[0]:d;
}
function fmtId(id){return id?id.substring(0,8)+'...':'-';}
function escHTML(s){
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toast(msg,tipo='info'){
    const c=document.getElementById('toast-container');
    const t=document.createElement('div');
    t.className=`toast ${tipo}`;
    const icons={success:'✅',error:'❌',info:'ℹ️',warning:'⚠️'};
    t.innerHTML=`<span>${icons[tipo]||'ℹ️'}</span><span>${escHTML(msg)}</span>`;
    c.appendChild(t);
    setTimeout(()=>{t.style.opacity='0';t.style.transition='opacity 0.3s';},3500);
    setTimeout(()=>t.remove(),3800);
}

function mostrarAlert(id,msg,tipo='error'){
    const el=document.getElementById(id);
    if(!el)return;
    el.textContent=msg;
    el.className=`alert alert-${tipo}`;
    el.style.display='block';
}

function fecharModal(id){document.getElementById(id).classList.remove('open');}
function abrirModal(id){document.getElementById(id).classList.add('open');}

document.querySelectorAll('.modal-overlay').forEach(m=>{
    m.addEventListener('click',e=>{if(e.target===m)fecharModal(m.id);});
});

// ==================== API ====================
async function api(path,opts={}){
    const headers={'Content-Type':'application/json'};
    if(E.token) headers['Authorization']='Bearer '+E.token;
    if(E.chaveSession) headers['X-Chave-Sessao']=E.chaveSession;
    try{
        const r=await fetch(path,{
            headers,credentials:'include',...opts,
            body:opts.body&&typeof opts.body!=='string'?JSON.stringify(opts.body):opts.body
        });
        return await r.json();
    }catch(err){return {erro:'Erro de conexão: '+err.message};}
}

async function apiForm(path,formData){
    const headers={};
    if(E.token) headers['Authorization']='Bearer '+E.token;
    if(E.chaveSession) headers['X-Chave-Sessao']=E.chaveSession;
    try{
        const r=await fetch(path,{method:'POST',headers,body:formData,credentials:'include'});
        return await r.json();
    }catch(err){return {erro:'Erro: '+err.message};}
}

// ==================== AUTH ====================
function trocarAbaAuth(aba){
    document.getElementById('form-login').style.display=aba==='login'?'block':'none';
    document.getElementById('form-registro').style.display=aba==='registro'?'block':'none';
    document.querySelectorAll('.auth-tab').forEach((t,i)=>
    t.classList.toggle('active',(i===0&&aba==='login')||(i===1&&aba==='registro'))
    );
}

async function fazerLogin(){
    const u=document.getElementById('login-user').value.trim();
    const p=document.getElementById('login-pass').value;
    if(!u||!p){mostrarAlert('alert-login','Preencha usuário e senha');return;}
    const btn=document.getElementById('btn-login');
    btn.innerHTML='<div class="loading"></div> Entrando...';btn.disabled=true;
    const r=await api('/api/login',{method:'POST',body:{username:u,password:p}});
    btn.innerHTML='Entrar';btn.disabled=false;
    if(r.erro){mostrarAlert('alert-login',r.erro);return;}
    E.token=r.token;E.user=r.username;E.isAdmin=r.is_admin;E.chaveSession=r.chave_sessao;
    iniciarApp(r.deve_trocar_senha);
}

async function fazerRegistro(){
    const u=document.getElementById('reg-user').value.trim();
    const p=document.getElementById('reg-pass').value;
    const p2=document.getElementById('reg-pass2').value;
    if(!u||!p){mostrarAlert('alert-reg','Preencha todos os campos');return;}
    if(p!==p2){mostrarAlert('alert-reg','Senhas não coincidem');return;}
    if(p.length<8){mostrarAlert('alert-reg','Mínimo 8 caracteres');return;}
    const btn=document.getElementById('btn-reg');
    btn.innerHTML='<div class="loading"></div>';btn.disabled=true;
    const r=await api('/api/registro',{method:'POST',body:{username:u,password:p}});
    btn.innerHTML='Criar Conta';btn.disabled=false;
    if(r.erro){mostrarAlert('alert-reg',r.erro,'error');return;}
    mostrarAlert('alert-reg','Conta criada! Faça login.','success');
    setTimeout(()=>trocarAbaAuth('login'),1500);
}

function iniciarApp(deveTrocar=false){
    document.getElementById('auth-screen').style.display='none';
    document.getElementById('app-screen').style.display='flex';
    document.getElementById('badge-user').textContent='👤 '+E.user;
    if(E.isAdmin){
        document.getElementById('badge-admin').style.display='inline';
        document.getElementById('sidebar-usuario').style.display='none';
        document.getElementById('sidebar-admin').style.display='flex';
        document.getElementById('ai-fab-btn').style.display='none';
        irParaAdmin('admin-usuarios');
    } else {
        document.getElementById('sidebar-usuario').style.display='flex';
        document.getElementById('sidebar-admin').style.display='none';
        document.getElementById('ai-fab-btn').style.display='flex';
        if(deveTrocar) document.getElementById('aviso-senha').style.display='flex';
        carregarCategorias().then(()=>{carregarDashboard();carregarModeloInfo();});
    }
}

function logout(){
    Object.assign(E,{token:null,user:null,isAdmin:false,chaveSession:null,transacoes:[],categorias:[]});
    document.getElementById('auth-screen').style.display='flex';
    document.getElementById('app-screen').style.display='none';
    document.getElementById('login-pass').value='';
    document.getElementById('aviso-senha').style.display='none';
}

// ==================== NAVEGAÇÃO ====================
const PAGES_USER=['dashboard','transacoes','categorias','emprestimos','projecoes','chat'];
const PAGES_ADMIN=['admin-usuarios','admin-sistema','admin-logs','admin-modelos','admin-backup'];

function irPara(pagina){
    [...PAGES_USER,...PAGES_ADMIN].forEach(p=>{
        document.getElementById('page-'+p)?.classList.remove('active');
    });
    document.querySelectorAll('#sidebar-usuario .nav-item').forEach(n=>n.classList.remove('active'));
    document.getElementById('page-'+pagina)?.classList.add('active');
    document.getElementById('nav-'+pagina)?.classList.add('active');
    E.paginaAtual=pagina;
    ({dashboard:carregarDashboard,transacoes:carregarTransacoes,
        categorias:carregarCategoriasUI,emprestimos:carregarEmprestimos,
        projecoes:carregarProjecoes})[pagina]?.();
}

function irParaAdmin(pagina){
    [...PAGES_USER,...PAGES_ADMIN].forEach(p=>{
        document.getElementById('page-'+p)?.classList.remove('active');
    });
    document.querySelectorAll('#sidebar-admin .nav-item').forEach(n=>n.classList.remove('active'));
    document.getElementById('page-'+pagina)?.classList.add('active');
    document.getElementById('nav-'+pagina)?.classList.add('active');
    E.paginaAtual=pagina;
    ({'admin-usuarios':carregarAdminUsuarios,'admin-sistema':carregarAdminSistema,
        'admin-logs':carregarAdminLogs,'admin-modelos':carregarAdminModelos,
        'admin-backup':renderizarAdminBackup})[pagina]?.();
}

// ==================== DASHBOARD ====================
async function carregarDashboard(){
    const [saldo,trans]=await Promise.all([api('/api/transacoes/saldo'),api('/api/transacoes?limite=10')]);
    if(saldo.saldo!==undefined){
        document.getElementById('val-entrada').textContent=fmtMoeda(saldo.total_entrada);
        document.getElementById('val-saida').textContent=fmtMoeda(saldo.total_saida);
        const saldoEl=document.getElementById('val-saldo');
        saldoEl.textContent=fmtMoeda(saldo.saldo);
        saldoEl.style.color=saldo.saldo>=0?'var(--entrada)':'var(--saida)';
        document.getElementById('val-qtd').textContent=saldo.quantidade||0;
    }
    if(trans.transacoes){E.transacoes=trans.transacoes;renderizarTabelaDash(trans.transacoes.slice(0,10));}
    const an=await api('/api/agente/anomalias');
    renderizarAlertasDash(an.anomalias||[]);
}

function renderizarTabelaDash(lista){
    const tb=document.getElementById('tb-dash');
    if(!lista.length){
        tb.innerHTML='<tr><td colspan="6" style="padding:40px;text-align:center;color:var(--text-muted)">Nenhuma transação ainda.</td></tr>';
        return;
    }
    tb.innerHTML=lista.map(t=>{
        const cat=E.categorias.find(c=>c.id===t.categoria_id);
        return `<tr>
        <td>${fmtData(t.data)}</td>
        <td><strong>${escHTML(t.nome_fantasia)}</strong></td>
        <td>${cat?`<span class="badge badge-${cat.tipo==='emprestimo'?'emp':cat.tipo==='quitacao'?'quit':'org'}">${escHTML(cat.nome)}</span>`:'<span style="color:var(--text-muted)">—</span>'}</td>
        <td><span class="badge badge-${t.tipo}">${t.tipo==='entrada'?'Entrada':'Saída'}</span></td>
        <td style="color:${t.tipo==='entrada'?'var(--entrada)':'var(--saida)'};font-weight:600">
        ${t.tipo==='entrada'?'+':'-'}${fmtMoeda(t.valor)}</td>
        <td><button class="btn-icon" onclick="abrirAnaliseTransacao('${t.id}')">🤖</button></td>
        </tr>`;
    }).join('');
}

function renderizarAlertasDash(anomalias){
    const div=document.getElementById('dash-alertas');
    if(!anomalias.length){div.innerHTML='';return;}
    div.innerHTML=anomalias.slice(0,3).map(a=>`
    <div class="alerta-anomalia">⚠️ Transação anômala: <strong>${escHTML(a.nome_fantasia||'')}</strong>
    — ${fmtMoeda(a.valor)} (${a.tipo}) — Severidade: <strong>${a.severidade}</strong></div>
    `).join('');
}

// ==================== TRANSAÇÕES ====================
async function carregarTransacoes(){
    const r=await api('/api/transacoes');
    if(r.transacoes){
        E.transacoes=r.transacoes;
        E.todosNomesFantasia=[...new Set(r.transacoes.map(t=>t.nome_fantasia).filter(Boolean))].sort();
        atualizarSelectCatFiltro();
        renderizarTransacoes(E.transacoes);
    }
}

async function filtrarTransacoes(){
    const f={};
    const nome=document.getElementById('f-nome').value;
    const desc=document.getElementById('f-desc').value;
    const tipo=document.getElementById('f-tipo').value;
    const cat=document.getElementById('f-cat').value;
    const ini=document.getElementById('f-data-ini').value;
    const fim=document.getElementById('f-data-fim').value;
    const vmin=document.getElementById('f-val-min').value;
    const vmax=document.getElementById('f-val-max').value;
    if(nome)f.nome_fantasia=nome;
    if(desc)f.descricao=desc;
    if(tipo)f.tipo=tipo;
    if(cat)f.categoria_id=cat;
    if(ini)f.data_inicio=ini;
    if(fim)f.data_fim=fim;
    if(vmin)f.valor_min=vmin;
    if(vmax)f.valor_max=vmax;
    const params=new URLSearchParams(f);
    const r=await api('/api/transacoes?'+params.toString());
    if(r.transacoes)renderizarTransacoes(r.transacoes);
}

function limparFiltros(){
    ['f-nome','f-desc','f-val-min','f-val-max'].forEach(id=>document.getElementById(id).value='');
    ['f-tipo','f-cat'].forEach(id=>document.getElementById(id).value='');
    ['f-data-ini','f-data-fim'].forEach(id=>document.getElementById(id).value='');
    carregarTransacoes();
}

function atualizarSelectCatFiltro(){
    const sel=document.getElementById('f-cat');
    const val=sel.value;
    sel.innerHTML='<option value="">Todas as categorias</option>'+
    E.categorias.filter(c=>c.tipo!=='emprestimo'||true).map(c=>
    `<option value="${c.id}">${escHTML(c.nome)}</option>`).join('');
    sel.value=val;
}

function renderizarTransacoes(lista){
    document.getElementById('t-count').textContent=lista.length+' transações';
    // Mostra totais do filtro
    const totalE=lista.filter(t=>t.tipo==='entrada').reduce((s,t)=>s+t.valor,0);
    const totalS=lista.filter(t=>t.tipo==='saida').reduce((s,t)=>s+t.valor,0);
    document.getElementById('t-total-filtro').innerHTML=
    `<span style="color:var(--entrada)">+${fmtMoeda(totalE)}</span> &nbsp;
    <span style="color:var(--saida)">-${fmtMoeda(totalS)}</span>`;
    const tb=document.getElementById('tb-trans');
    if(!lista.length){
        tb.innerHTML=`<tr><td colspan="8"><div class="empty-state">
        <div class="empty-icon">💳</div>
        <div class="empty-title">Nenhuma transação encontrada</div></div></td></tr>`;
        return;
    }
    tb.innerHTML=lista.map(t=>{
        const cat=E.categorias.find(c=>c.id===t.categoria_id);
        return `<tr>
        <td style="color:var(--text-muted);font-family:monospace;font-size:11px">${fmtId(t.id)}</td>
        <td>${fmtData(t.data)}</td>
        <td><strong>${escHTML(t.nome_fantasia)}</strong></td>
        <td style="color:var(--text-secondary);max-width:160px;overflow:hidden;
        text-overflow:ellipsis;white-space:nowrap" title="${escHTML(t.descricao||'')}">
        ${escHTML(t.descricao||'—')}</td>
        <td>
        ${cat
            ?`<span class="badge badge-${cat.tipo==='emprestimo'?'emp':cat.tipo==='quitacao'?'quit':'org'}"
            style="cursor:pointer" onclick="abrirMoverTransacao('${t.id}','${escHTML(t.nome_fantasia)}')"
            title="Clique para mover">${escHTML(cat.nome)} ↔</span>`
            :`<button class="btn btn-ghost btn-sm" onclick="abrirMoverTransacao('${t.id}','${escHTML(t.nome_fantasia)}')">+ Cat</button>`
        }
        </td>
        <td><span class="badge badge-${t.tipo}">${t.tipo==='entrada'?'Entrada':'Saída'}</span></td>
        <td style="color:${t.tipo==='entrada'?'var(--entrada)':'var(--saida)'};font-weight:700;white-space:nowrap">
        ${t.tipo==='entrada'?'+':'-'}${fmtMoeda(t.valor)}</td>
        <td>
        <div style="display:flex;gap:2px">
        <button class="btn-icon" onclick="editarTransacao('${t.id}')" title="Editar">✏️</button>
        <button class="btn-icon" onclick="abrirMoverTransacao('${t.id}','${escHTML(t.nome_fantasia)}')" title="Mover categoria">↔️</button>
        <button class="btn-icon" onclick="abrirAnaliseTransacao('${t.id}')" title="Analisar IA">🤖</button>
        <button class="btn-icon" onclick="excluirTransacao('${t.id}')"
        style="color:var(--danger)" title="Excluir">🗑️</button>
        </div>
        </td>
        </tr>`;
    }).join('');
}

// Mover / Atribuir categoria a transação
function abrirMoverTransacao(transId, nome){
    E.transMover=transId;
    document.getElementById('mmt-info').textContent=`Transação: "${nome}"`;
    document.getElementById('mmt-alert').style.display='none';
    const sel=document.getElementById('mmt-cat');
    sel.innerHTML='<option value="">Sem categoria (remover)</option>'+
    E.categorias.map(c=>`<option value="${c.id}">${escHTML(c.nome)} (${c.tipo})</option>`).join('');
    // Pré-seleciona categoria atual
    const t=E.transacoes.find(x=>x.id===transId);
    if(t?.categoria_id) sel.value=t.categoria_id;
    abrirModal('modal-mover-trans');
}

async function confirmarMoverTransacao(){
    const catId=document.getElementById('mmt-cat').value||null;
    const r=await api(`/api/transacoes/${E.transMover}/categoria`,{
        method:'PUT',body:{categoria_id:catId}
    });
    if(r.sucesso){
        toast('Categoria atualizada!','success');
        fecharModal('modal-mover-trans');
        await carregarCategorias();
        carregarTransacoes();
    } else mostrarAlert('mmt-alert',r.erro||'Erro','error');
}

function abrirModalTransacao(transacao=null){
    E.transacaoEditando=transacao;
    document.getElementById('mt-title').textContent=transacao?'Editar Transação':'Nova Transação';
    document.getElementById('mt-alert').style.display='none';
    const sel=document.getElementById('mt-cat');
    sel.innerHTML='<option value="">Sem categoria</option>'+
    E.categorias.map(c=>`<option value="${c.id}">${escHTML(c.nome)}</option>`).join('');
    if(transacao){
        document.getElementById('mt-tipo').value=transacao.tipo;
        document.getElementById('mt-valor').value=transacao.valor;
        document.getElementById('mt-nome').value=transacao.nome_fantasia;
        document.getElementById('mt-desc').value=transacao.descricao||'';
        document.getElementById('mt-cat').value=transacao.categoria_id||'';
        document.getElementById('mt-data').value=transacao.data||'';
    } else {
        document.getElementById('mt-tipo').value='saida';
        ['mt-valor','mt-nome','mt-desc'].forEach(id=>document.getElementById(id).value='');
        document.getElementById('mt-cat').value='';
        document.getElementById('mt-data').value=new Date().toISOString().split('T')[0];
    }
    abrirModal('modal-transacao');
}

async function salvarTransacao(){
    const dados={
        tipo:document.getElementById('mt-tipo').value,
        valor:parseFloat(document.getElementById('mt-valor').value),
        nome_fantasia:document.getElementById('mt-nome').value.trim(),
        descricao:document.getElementById('mt-desc').value.trim(),
        categoria_id:document.getElementById('mt-cat').value||null,
        data:document.getElementById('mt-data').value,
    };
    if(!dados.nome_fantasia){mostrarAlert('mt-alert','Informe o nome fantasia');return;}
    if(!dados.valor||dados.valor<=0){mostrarAlert('mt-alert','Valor inválido');return;}
    const btn=document.getElementById('btn-salvar-t');
    btn.innerHTML='<div class="loading"></div>';btn.disabled=true;
    const r=E.transacaoEditando
    ?await api('/api/transacoes/'+E.transacaoEditando.id,{method:'PUT',body:dados})
    :await api('/api/transacoes',{method:'POST',body:dados});
    btn.innerHTML='Salvar';btn.disabled=false;
    if(r.erro){mostrarAlert('mt-alert',r.erro);return;}
    toast(E.transacaoEditando?'Transação atualizada!':'Transação adicionada!','success');
    fecharModal('modal-transacao');
    await carregarCategorias();
    if(E.paginaAtual==='dashboard') carregarDashboard();
    else carregarTransacoes();
}

function editarTransacao(id){
    const t=E.transacoes.find(x=>x.id===id);
    if(t) abrirModalTransacao(t);
}

async function excluirTransacao(id){
    if(!confirm('Excluir esta transação?'))return;
    const r=await api('/api/transacoes/'+id,{method:'DELETE'});
    if(r.sucesso){
        toast('Transação excluída','success');
        if(E.paginaAtual==='transacoes') carregarTransacoes();
        else carregarDashboard();
    } else toast(r.erro||'Erro','error');
}

// ==================== CATEGORIAS ====================
async function carregarCategorias(){
    const r=await api('/api/categorias');
    if(r.categorias) E.categorias=r.categorias;
}

async function carregarCategoriasUI(){
    await carregarCategorias();
    const rn=await api('/api/transacoes/nomes-fantasia');
    if(rn.nomes) E.todosNomesFantasia=rn.nomes;
    const div=document.getElementById('lista-categorias');
    // Exibe apenas organizacao e quitacao (emprestimos têm página própria)
    const cats=E.categorias.filter(c=>c.tipo!=='emprestimo');
    if(!cats.length){
        div.innerHTML=`<div class="empty-state">
        <div class="empty-icon">🏷️</div>
        <div class="empty-title">Nenhuma categoria criada</div>
        <button class="btn btn-primary" style="margin-top:16px" onclick="abrirModalCategoria()">+ Criar Categoria</button>
        </div>`;return;
    }
    div.innerHTML=cats.map(cat=>renderizarCardCategoria(cat)).join('');
}

function renderizarCardCategoria(cat){
    const pct=cat.tipo==='quitacao'&&cat.meta_valor?Math.min(100,cat.percentual_quitado||0):null;
    return `<div class="analise-card">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px">
    <div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <strong style="font-size:15px">${escHTML(cat.nome)}</strong>
    <span class="badge badge-${cat.tipo==='quitacao'?'quit':'org'}">
    ${cat.tipo==='quitacao'?'💳 Quitação':'📁 Organização'}</span>
    </div>
    ${cat.descricao?`<p style="color:var(--text-secondary);font-size:12px">${escHTML(cat.descricao)}</p>`:''}
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
    <button class="btn btn-ghost btn-sm" onclick="abrirDetalheCategoria('${cat.id}')">📋 Ver</button>
    <button class="btn btn-ghost btn-sm" onclick="abrirModalCategoria('${cat.id}')">✏️ Editar</button>
    <button class="btn btn-danger btn-sm" onclick="excluirCategoria('${cat.id}')">🗑️</button>
    </div>
    </div>
    <div style="display:flex;gap:24px;margin-top:12px;flex-wrap:wrap">
    <div><span style="color:var(--text-muted);font-size:12px">Entradas</span>
    <div style="color:var(--entrada);font-weight:600">${fmtMoeda(cat.total_entrada)}</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Saídas</span>
    <div style="color:var(--saida);font-weight:600">${fmtMoeda(cat.total_saida)}</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Saldo</span>
    <div style="color:${cat.saldo>=0?'var(--entrada)':'var(--saida)'};font-weight:600">${fmtMoeda(cat.saldo)}</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Transações</span>
    <div style="font-weight:600">${cat.qtd_transacoes}</div></div>
    </div>
    ${pct!==null?`
        <div style="margin-top:12px">
        <div style="display:flex;justify-content:space-between;font-size:12px;
        color:var(--text-secondary);margin-bottom:4px">
        <span>Meta: ${fmtMoeda(cat.meta_valor)}</span>
        <span>${pct.toFixed(1)}% — Restante: ${fmtMoeda(cat.valor_restante||0)}</span>
        </div>
        <div class="progress-bar">
        <div class="progress-fill" style="width:${pct}%;
        background:${pct>=100?'var(--success)':pct>=70?'var(--warning)':'var(--accent)'}"></div>
        </div>
        </div>`:''}
        ${cat.nomes_fantasia?.length?`
            <div style="margin-top:10px">
            <span style="color:var(--text-muted);font-size:11px;display:block;margin-bottom:4px">NOMES VINCULADOS:</span>
            <div style="display:flex;flex-wrap:wrap;gap:4px">
            ${cat.nomes_fantasia.map(n=>`<span class="chip">${escHTML(n)}
            <span class="chip-remove" onclick="removerNomeFantasia('${cat.id}','${escHTML(n.replace(/'/g,"\\'"))}')">×</span>
            </span>`).join('')}
            </div>
            </div>`:`<div style="margin-top:8px;color:var(--text-muted);font-size:12px">
            Nenhum nome vinculado. <button class="btn btn-ghost btn-sm" style="margin-left:4px"
            onclick="abrirModalCategoria('${cat.id}')">+ Vincular</button></div>`}
            </div>`;
}

function toggleTipoCategoria(){
    const tipo=document.getElementById('mc-tipo').value;
    document.getElementById('fg-meta-valor').style.display=tipo==='quitacao'?'block':'none';
    document.getElementById('fg-emprestimo').style.display=tipo==='emprestimo'?'block':'none';
}

function calcularTotalEmprestimo(){
    const valor=parseFloat(document.getElementById('mc-emp-valor').value)||0;
    const juros=parseFloat(document.getElementById('mc-emp-juros').value)||0;
    const parcelas=parseInt(document.getElementById('mc-emp-parcelas').value)||1;
    const desconto=parseFloat(document.getElementById('mc-emp-desconto').value)||0;
    if(valor<=0){document.getElementById('emp-resumo').style.display='none';return;}
    let totalJuros=valor;
    if(juros>0){
        // Juros compostos: P * (1+i)^n
        totalJuros=valor*Math.pow(1+juros/100,parcelas);
    }
    const totalFinal=Math.max(0,totalJuros-desconto);
    const parcelaVal=totalFinal/parcelas;
    document.getElementById('emp-total-juros').textContent=fmtMoeda(totalJuros);
    document.getElementById('emp-total-desc').textContent='-'+fmtMoeda(desconto);
    document.getElementById('emp-total-final').textContent=fmtMoeda(totalFinal);
    document.getElementById('emp-parcela-val').textContent=fmtMoeda(parcelaVal);
    document.getElementById('emp-resumo').style.display='block';
}

async function abrirModalCategoria(catId=null, tipoForcado=null){
    E.categoriaEditando=catId?E.categorias.find(c=>c.id===catId):null;
    E.nomesSelecionados=E.categoriaEditando?[...(E.categoriaEditando.nomes_fantasia||[])]:[];
    document.getElementById('mc-title').textContent=E.categoriaEditando?'Editar Categoria':'Nova Categoria';
    document.getElementById('mc-alert').style.display='none';
    document.getElementById('mc-nome-input').value='';
    if(E.categoriaEditando){
        document.getElementById('mc-nome').value=E.categoriaEditando.nome;
        document.getElementById('mc-tipo').value=E.categoriaEditando.tipo;
        document.getElementById('mc-meta').value=E.categoriaEditando.meta_valor||'';
        document.getElementById('mc-desc').value=E.categoriaEditando.descricao||'';
        // Campos empréstimo
        if(E.categoriaEditando.tipo==='emprestimo'&&E.categoriaEditando.emp_dados){
            const d=E.categoriaEditando.emp_dados;
            document.getElementById('mc-emp-valor').value=d.valor_principal||'';
            document.getElementById('mc-emp-juros').value=d.juros_pct||0;
            document.getElementById('mc-emp-parcelas').value=d.parcelas||1;
            document.getElementById('mc-emp-desconto').value=d.desconto||0;
        }
    } else {
        document.getElementById('mc-nome').value='';
        document.getElementById('mc-tipo').value=tipoForcado||'organizacao';
        document.getElementById('mc-meta').value='';
        document.getElementById('mc-desc').value='';
        document.getElementById('mc-emp-valor').value='';
        document.getElementById('mc-emp-juros').value='0';
        document.getElementById('mc-emp-parcelas').value='1';
        document.getElementById('mc-emp-desconto').value='0';
    }
    toggleTipoCategoria();
    if(E.todosNomesFantasia.length===0){
        const rn=await api('/api/transacoes/nomes-fantasia');
        if(rn.nomes) E.todosNomesFantasia=rn.nomes;
    }
    renderizarNomesSelecionados();
    renderizarSugestoesNomes('');
    abrirModal('modal-categoria');
}

function renderizarNomesSelecionados(){
    const div=document.getElementById('mc-nomes-selecionados');
    if(!E.nomesSelecionados.length){
        div.innerHTML='<span style="color:var(--text-muted);font-size:12px">Nenhum nome vinculado</span>';return;
    }
    div.innerHTML=E.nomesSelecionados.map(n=>`
    <span class="chip">${escHTML(n)}
    <span class="chip-remove" onclick="removerNomeSelecionado('${escHTML(n.replace(/'/g,"\\'"))}')">×</span>
    </span>`).join('');
}

function renderizarSugestoesNomes(filtro){
    const div=document.getElementById('mc-sugestoes-nomes');
    const termoL=filtro.toLowerCase();
    const disponiveis=E.todosNomesFantasia.filter(n=>
    !E.nomesSelecionados.includes(n)&&(termoL===''||n.toLowerCase().includes(termoL))
    );
    if(!E.todosNomesFantasia.length){
        div.innerHTML='<span style="color:var(--text-muted);font-size:12px">Adicione transações primeiro</span>';return;
    }
    if(!disponiveis.length){
        div.innerHTML='<span style="color:var(--text-muted);font-size:12px">Todos os nomes já vinculados</span>';return;
    }
    div.innerHTML=disponiveis.map(n=>
    `<span class="nome-chip" onclick="selecionarNome('${escHTML(n.replace(/'/g,"\\'"))}')">
    ${escHTML(n)}</span>`).join('');
}

function filtrarNomesSugestao(){renderizarSugestoesNomes(document.getElementById('mc-nome-input').value);}
function selecionarNome(nome){
    if(!E.nomesSelecionados.includes(nome)){E.nomesSelecionados.push(nome);}
    renderizarNomesSelecionados();
    renderizarSugestoesNomes(document.getElementById('mc-nome-input').value);
}
function removerNomeSelecionado(nome){
    E.nomesSelecionados=E.nomesSelecionados.filter(n=>n!==nome);
    renderizarNomesSelecionados();
    renderizarSugestoesNomes(document.getElementById('mc-nome-input').value);
}
function adicionarNomeManual(){
    const input=document.getElementById('mc-nome-input');
    const nome=input.value.trim();
    if(!nome)return;
    if(!E.nomesSelecionados.includes(nome)) E.nomesSelecionados.push(nome);
    input.value='';renderizarNomesSelecionados();renderizarSugestoesNomes('');
}

async function salvarCategoria(){
    const tipo=document.getElementById('mc-tipo').value;
    const dados={
        nome:document.getElementById('mc-nome').value.trim(),
        tipo,
        descricao:document.getElementById('mc-desc').value.trim(),
        nomes_fantasia:E.nomesSelecionados,
    };
    if(!dados.nome){mostrarAlert('mc-alert','Informe o nome');return;}
    if(tipo==='quitacao'){
        const meta=document.getElementById('mc-meta').value;
        if(!meta){mostrarAlert('mc-alert','Informe o valor da dívida');return;}
        dados.meta_valor=parseFloat(meta);
    }
    if(tipo==='emprestimo'){
        const valor=parseFloat(document.getElementById('mc-emp-valor').value);
        if(!valor||valor<=0){mostrarAlert('mc-alert','Informe o valor do empréstimo');return;}
        dados.emp_dados={
            valor_principal:valor,
            juros_pct:parseFloat(document.getElementById('mc-emp-juros').value)||0,
            parcelas:parseInt(document.getElementById('mc-emp-parcelas').value)||1,
            desconto:parseFloat(document.getElementById('mc-emp-desconto').value)||0,
        };
        // Calcula total a pagar
        const j=dados.emp_dados.juros_pct;
        const p=dados.emp_dados.parcelas;
        const totalJuros=j>0?valor*Math.pow(1+j/100,p):valor;
        dados.emp_dados.total_a_pagar=Math.max(0,totalJuros-dados.emp_dados.desconto);
        dados.emp_dados.valor_parcela=dados.emp_dados.total_a_pagar/p;
        dados.meta_valor=dados.emp_dados.total_a_pagar;
    }
    const btn=document.getElementById('btn-salvar-c');
    btn.innerHTML='<div class="loading"></div>';btn.disabled=true;
    let r;
    if(E.categoriaEditando){
        r=await api('/api/categorias/'+E.categoriaEditando.id,{method:'PUT',body:dados});
    } else {
        r=await api('/api/categorias',{method:'POST',body:dados});
    }
    btn.innerHTML='Salvar';btn.disabled=false;
    if(r.erro){mostrarAlert('mc-alert',r.erro);return;}

    const catId=r.categoria_id||E.categoriaEditando?.id;
    if(catId){
        // Sincroniza nomes fantasia
        if(E.categoriaEditando){
            const removidos=(E.categoriaEditando.nomes_fantasia||[]).filter(n=>!E.nomesSelecionados.includes(n));
            const novos=E.nomesSelecionados.filter(n=>!(E.categoriaEditando.nomes_fantasia||[]).includes(n));
            for(const nome of removidos)
                await api(`/api/categorias/${catId}/nomes-fantasia`,{method:'DELETE',body:{nome_fantasia:nome}});
            for(const nome of novos)
                await api(`/api/categorias/${catId}/nomes-fantasia`,{method:'POST',body:{nome_fantasia:nome}});
        } else {
            for(const nome of E.nomesSelecionados)
                await api(`/api/categorias/${catId}/nomes-fantasia`,{method:'POST',body:{nome_fantasia:nome}});
        }
    }
    toast('Categoria salva!','success');
    fecharModal('modal-categoria');
    await carregarCategorias();
    if(E.paginaAtual==='categorias') carregarCategoriasUI();
    else if(E.paginaAtual==='emprestimos') carregarEmprestimos();
}

async function excluirCategoria(id){
    if(!confirm('Excluir esta categoria?'))return;
    const r=await api('/api/categorias/'+id,{method:'DELETE'});
    if(r.sucesso){toast('Categoria excluída','success');await carregarCategorias();carregarCategoriasUI();}
    else toast(r.erro||'Erro','error');
}

async function removerNomeFantasia(catId,nome){
    const r=await api(`/api/categorias/${catId}/nomes-fantasia`,{method:'DELETE',body:{nome_fantasia:nome}});
    if(r.sucesso){toast('Nome removido','info');await carregarCategorias();carregarCategoriasUI();}
}

async function abrirDetalheCategoria(catId){
    const cat=E.categorias.find(c=>c.id===catId);
    if(!cat)return;
    document.getElementById('mcd-title').textContent='📁 '+cat.nome;
    document.getElementById('mcd-content').innerHTML=
    '<div style="text-align:center;padding:20px"><div class="loading"></div></div>';
    abrirModal('modal-cat-detalhe');
    const r=await api('/api/transacoes?categoria_id='+catId);
    const trans=r.transacoes||[];
    let html=`<div style="display:flex;gap:24px;margin-bottom:16px;flex-wrap:wrap">
    <div><span style="color:var(--text-muted);font-size:12px">Entradas</span>
    <div style="color:var(--entrada);font-weight:700;font-size:18px">${fmtMoeda(cat.total_entrada)}</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Saídas</span>
    <div style="color:var(--saida);font-weight:700;font-size:18px">${fmtMoeda(cat.total_saida)}</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Saldo</span>
    <div style="color:${cat.saldo>=0?'var(--entrada)':'var(--saida)'};font-weight:700;font-size:18px">
    ${fmtMoeda(cat.saldo)}</div></div>
    </div>`;
    if(cat.tipo==='quitacao'&&cat.meta_valor){
        const pct=Math.min(100,cat.percentual_quitado||0);
        html+=`<div style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-secondary);margin-bottom:4px">
        <span>Meta: ${fmtMoeda(cat.meta_valor)}</span>
        <span>${pct.toFixed(1)}% — Restante: ${fmtMoeda(cat.valor_restante||0)}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
        </div>`;
    }
    // Lista transações com opção de remover da categoria
    html+=`<div style="max-height:400px;overflow-y:auto">
    <table style="width:100%">
    <thead><tr>
    <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px">Data</th>
    <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px">Nome</th>
    <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px">Tipo</th>
    <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px;text-align:right">Valor</th>
    <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px">Ação</th>
    </tr></thead>
    <tbody>${!trans.length
        ?'<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">Nenhuma transação</td></tr>'
        :trans.map(t=>`<tr style="border-top:1px solid var(--border)">
        <td style="padding:8px;font-size:12px;color:var(--text-muted)">${fmtData(t.data)}</td>
        <td style="padding:8px;font-size:12px">${escHTML(t.nome_fantasia)}</td>
        <td style="padding:8px"><span class="badge badge-${t.tipo}" style="font-size:10px">${t.tipo}</span></td>
        <td style="padding:8px;text-align:right;color:${t.tipo==='entrada'?'var(--entrada)':'var(--saida)'};font-weight:600">
        ${t.tipo==='entrada'?'+':'-'}${fmtMoeda(t.valor)}</td>
        <td style="padding:8px">
        <button class="btn btn-ghost btn-sm" style="font-size:10px"
        onclick="removerTransacaoDeCategoria('${t.id}')">↔ Mover</button>
        </td>
        </tr>`).join('')}
        </tbody>
        </table>
        </div>`;
        document.getElementById('mcd-content').innerHTML=html;
}

async function removerTransacaoDeCategoria(transId){
    const r=await api(`/api/transacoes/${transId}/categoria`,{method:'PUT',body:{categoria_id:null}});
    if(r.sucesso){
        toast('Transação removida da categoria','info');
        await carregarCategorias();
        fecharModal('modal-cat-detalhe');
    } else toast(r.erro||'Erro','error');
}

// ==================== EMPRÉSTIMOS ====================
async function carregarEmprestimos(){
    await carregarCategorias();
    const emprestimos=E.categorias.filter(c=>c.tipo==='emprestimo');
    const ativos=emprestimos.filter(e=>!e.emp_dados?.quitado);
    const quitados=emprestimos.filter(e=>e.emp_dados?.quitado);
    renderizarEmprestimos(ativos,'emp-ativos');
    renderizarEmprestimos(quitados,'emp-quitados');
}

function renderizarEmprestimos(lista,divId){
    const div=document.getElementById(divId);
    if(!lista.length){
        div.innerHTML=`<div class="empty-state">
        <div class="empty-icon">🤝</div>
        <div class="empty-title">${divId==='emp-ativos'?'Nenhum empréstimo ativo':'Nenhum empréstimo quitado'}</div>
        ${divId==='emp-ativos'?'<button class="btn btn-warning" style="margin-top:16px" onclick="abrirModalCategoria(null,\'emprestimo\')">+ Registrar Empréstimo</button>':''}
        </div>`;return;
    }
    div.innerHTML=lista.map(emp=>{
        const d=emp.emp_dados||{};
        const pago=emp.total_saida||0;
        const total=d.total_a_pagar||emp.meta_valor||0;
        const pct=total>0?Math.min(100,(pago/total)*100):0;
        return `<div class="emp-card ${d.quitado?'quitado':''}">
        <div class="emp-header">
        <div>
        <strong style="font-size:15px">${escHTML(emp.nome)}</strong>
        <span class="emp-status ${d.quitado?'quitado':'ativo'}" style="margin-left:8px">
        ${d.quitado?'✓ Quitado':'● Ativo'}</span>
        ${emp.descricao?`<p style="color:var(--text-secondary);font-size:12px;margin-top:4px">${escHTML(emp.descricao)}</p>`:''}
        </div>
        <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="abrirDetalheEmprestimo('${emp.id}')">📋 Detalhes</button>
        ${!d.quitado?`<button class="btn btn-ghost btn-sm" onclick="abrirModalCategoria('${emp.id}')">✏️</button>`:''}
        </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:12px">
        <div><span style="color:var(--text-muted);font-size:12px">Valor Emprestado</span>
        <div style="color:var(--entrada);font-weight:600">${fmtMoeda(d.valor_principal||0)}</div></div>
        <div><span style="color:var(--text-muted);font-size:12px">Total a Pagar</span>
        <div style="color:var(--warning);font-weight:600">${fmtMoeda(total)}</div></div>
        <div><span style="color:var(--text-muted);font-size:12px">Juros</span>
        <div style="font-weight:600">${d.juros_pct||0}% a.m.</div></div>
        <div><span style="color:var(--text-muted);font-size:12px">Parcelas</span>
        <div style="font-weight:600">${d.parcelas||1}x ${fmtMoeda(d.valor_parcela||0)}</div></div>
        <div><span style="color:var(--text-muted);font-size:12px">Já Pago</span>
        <div style="color:var(--saida);font-weight:600">${fmtMoeda(pago)}</div></div>
        <div><span style="color:var(--text-muted);font-size:12px">Restante</span>
        <div style="color:${total-pago>0?'var(--warning)':'var(--success)'};font-weight:700">
        ${fmtMoeda(Math.max(0,total-pago))}</div></div>
        </div>
        <div class="progress-bar">
        <div class="progress-fill" style="width:${pct}%;
        background:${pct>=100?'var(--success)':pct>=70?'var(--warning)':'var(--accent)'}"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;
        color:var(--text-muted);margin-top:4px">
        <span>${pct.toFixed(1)}% pago</span>
        <span>${emp.qtd_transacoes} pagamentos registrados</span>
        </div>
        </div>`;
    }).join('');
}

async function abrirDetalheEmprestimo(catId){
    E.empAtual=catId;
    const emp=E.categorias.find(c=>c.id===catId);
    if(!emp)return;
    document.getElementById('med-title').textContent='🤝 '+emp.nome;
    document.getElementById('med-content').innerHTML=
    '<div style="text-align:center;padding:20px"><div class="loading"></div></div>';
    const btnQuitar=document.getElementById('btn-quitar-emp');
    const d=emp.emp_dados||{};
    btnQuitar.style.display=d.quitado?'none':'inline-flex';
    abrirModal('modal-emp-detalhe');
    const r=await api('/api/transacoes?categoria_id='+catId);
    const trans=r.transacoes||[];
    const pago=trans.filter(t=>t.tipo==='saida').reduce((s,t)=>s+t.valor,0);
    const total=d.total_a_pagar||emp.meta_valor||0;
    const pct=total>0?Math.min(100,(pago/total)*100):0;
    document.getElementById('med-content').innerHTML=`
    <div style="background:var(--bg-tertiary);border-radius:var(--radius);padding:16px;margin-bottom:16px">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
    <div><span style="color:var(--text-muted);font-size:12px">Valor Principal</span>
    <div style="font-weight:700;font-size:16px">${fmtMoeda(d.valor_principal||0)}</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Total a Pagar</span>
    <div style="color:var(--warning);font-weight:700;font-size:16px">${fmtMoeda(total)}</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Juros</span>
    <div>${d.juros_pct||0}% ao mês</div></div>
    <div><span style="color:var(--text-muted);font-size:12px">Parcelas</span>
    <div>${d.parcelas||1}x de ${fmtMoeda(d.valor_parcela||0)}</div></div>
    ${d.desconto>0?`<div><span style="color:var(--text-muted);font-size:12px">Desconto</span>
        <div style="color:var(--success)">${fmtMoeda(d.desconto)}</div></div>`:''}
        </div>
        <div style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;font-size:12px;
        color:var(--text-secondary);margin-bottom:4px">
        <span>Progresso: ${fmtMoeda(pago)} pago de ${fmtMoeda(total)}</span>
        <span>${pct.toFixed(1)}%</span>
        </div>
        <div class="progress-bar">
        <div class="progress-fill" style="width:${pct}%;
        background:${pct>=100?'var(--success)':pct>=70?'var(--warning)':'var(--accent)'}"></div>
        </div>
        </div>
        <div style="display:flex;justify-content:space-between">
        <span style="color:var(--text-muted);font-size:13px">Já pago:</span>
        <strong style="color:var(--saida)">${fmtMoeda(pago)}</strong>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:4px">
        <span style="color:var(--text-muted);font-size:13px">Restante:</span>
        <strong style="color:${total-pago>0?'var(--warning)':'var(--success)'}">
        ${fmtMoeda(Math.max(0,total-pago))}</strong>
        </div>
        </div>
        <div style="max-height:300px;overflow-y:auto">
        <table style="width:100%">
        <thead><tr>
        <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px">Data</th>
        <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px">Nome</th>
        <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px">Tipo</th>
        <th style="padding:8px;background:var(--bg-tertiary);color:var(--text-muted);font-size:11px;text-align:right">Valor</th>
        <th style="padding:8px;background:var(--bg-tertiary);font-size:11px">Ação</th>
        </tr></thead>
        <tbody>${!trans.length
            ?'<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">Nenhum pagamento registrado</td></tr>'
            :trans.map(t=>`<tr style="border-top:1px solid var(--border)">
            <td style="padding:8px;font-size:12px;color:var(--text-muted)">${fmtData(t.data)}</td>
            <td style="padding:8px;font-size:12px">${escHTML(t.nome_fantasia)}</td>
            <td style="padding:8px"><span class="badge badge-${t.tipo}" style="font-size:10px">${t.tipo}</span></td>
            <td style="padding:8px;text-align:right;color:${t.tipo==='entrada'?'var(--entrada)':'var(--saida)'};font-weight:600">
            ${t.tipo==='entrada'?'+':'-'}${fmtMoeda(t.valor)}</td>
            <td style="padding:8px">
            <button class="btn btn-ghost btn-sm" style="font-size:10px"
            onclick="removerTransacaoDeCategoria('${t.id}')">↔ Mover</button>
            </td>
            </tr>`).join('')}
            </tbody>
            </table>
            </div>
            `;
}

async function quitarEmprestimo(){
    if(!E.empAtual)return;
    if(!confirm('Marcar este empréstimo como quitado? Ele será movido para o histórico.'))return;
    const r=await api(`/api/categorias/${E.empAtual}/quitar`,{method:'POST'});
    if(r.sucesso){
        toast('Empréstimo quitado!','success');
        fecharModal('modal-emp-detalhe');
        await carregarCategorias();
        carregarEmprestimos();
    } else toast(r.erro||'Erro','error');
}

function trocarTabEmp(tab,el){
    document.querySelectorAll('#page-emprestimos .tab').forEach(t=>t.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('emp-ativos').style.display=tab==='ativos'?'block':'none';
    document.getElementById('emp-quitados').style.display=tab==='quitados'?'block':'none';
}

// ==================== PROJEÇÕES ====================
function trocarTabProj(tab,el){
    document.querySelectorAll('#page-projecoes .tab').forEach(t=>t.classList.remove('active'));
    el.classList.add('active');
    ['tendencia','projecao','historico'].forEach(t=>
    document.getElementById('proj-'+t).style.display=t===tab?'block':'none');
}

async function carregarProjecoes(){
    document.getElementById('proj-tendencia').innerHTML=
    '<div style="text-align:center;padding:40px"><div class="loading" style="width:32px;height:32px;border-width:3px;margin:0 auto 12px"></div>Analisando...</div>';
    const r=await api('/api/agente/projecao?meses=3');
    const tend=r.tendencia||{};
    document.getElementById('proj-tendencia').innerHTML=`
    <div class="analise-card">
    <div class="analise-title">📊 Tendências Financeiras</div>
    ${(tend.alertas||[]).map(a=>`<div class="alerta-anomalia">${escHTML(a)}</div>`).join('')}
    <div class="analise-item"><span>Tendência de Gastos</span>
    <span style="font-weight:600;color:${tend.tendencia_gastos==='crescimento'?'var(--saida)':tend.tendencia_gastos==='queda'?'var(--entrada)':'var(--accent)'}">
    ${tend.tendencia_gastos==='crescimento'?'📈 Crescimento':tend.tendencia_gastos==='queda'?'📉 Queda':'➡️ Estável'}</span></div>
    <div class="analise-item"><span>Variação de Gastos</span>
    <span style="font-weight:600">${(tend.variacao_gastos_pct||0)>=0?'+':''}${tend.variacao_gastos_pct||0}%</span></div>
    <div class="analise-item"><span>Tendência de Receitas</span>
    <span style="font-weight:600;color:${tend.tendencia_receitas==='crescimento'?'var(--entrada)':tend.tendencia_receitas==='queda'?'var(--saida)':'var(--accent)'}">
    ${tend.tendencia_receitas==='crescimento'?'📈 Crescimento':tend.tendencia_receitas==='queda'?'📉 Queda':'➡️ Estável'}</span></div>
    <div class="analise-item"><span>Variação de Receitas</span>
    <span style="font-weight:600">${(tend.variacao_receitas_pct||0)>=0?'+':''}${tend.variacao_receitas_pct||0}%</span></div>
    </div>
    ${r.projecao_ia?.observacao?`<div class="analise-card">
        <div class="analise-title">🤖 Insight da IA</div>
        <p style="color:var(--text-secondary);font-size:13px">${escHTML(r.projecao_ia.observacao)}</p>
        </div>`:''}`;

        document.getElementById('proj-projecao').innerHTML=`
        <div class="analise-card">
        <div class="analise-title">🔮 Projeção dos Próximos 3 Meses</div>
        ${!(r.projecoes||[]).length?'<p style="color:var(--text-muted)">Dados insuficientes</p>':
            r.projecoes.map(p=>`<div style="margin-bottom:16px;padding:16px;background:var(--bg-tertiary);border-radius:var(--radius)">
            <div style="font-weight:600;margin-bottom:10px;color:var(--accent)">${p.mes}</div>
            <div style="display:flex;gap:24px;flex-wrap:wrap">
            <div><span style="color:var(--text-muted);font-size:12px">Entrada</span>
            <div style="color:var(--entrada);font-weight:600">${fmtMoeda(p.entrada)}</div></div>
            <div><span style="color:var(--text-muted);font-size:12px">Saída</span>
            <div style="color:var(--saida);font-weight:600">${fmtMoeda(p.saida)}</div></div>
            <div><span style="color:var(--text-muted);font-size:12px">Saldo</span>
            <div style="color:${p.saldo>=0?'var(--entrada)':'var(--saida)'};font-weight:700">${fmtMoeda(p.saldo)}</div></div>
            </div>
            </div>`).join('')}
            </div>`;

            const hist=r.historico_mensal||{};
            const meses=Object.keys(hist).sort().reverse();
            document.getElementById('proj-historico').innerHTML=`
            <div class="table-container">
            <div class="table-header"><span style="font-weight:600">Histórico Mensal</span></div>
            <table><thead><tr><th>Mês</th><th>Entradas</th><th>Saídas</th><th>Saldo</th><th>Transações</th></tr></thead>
            <tbody>${!meses.length?'<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">Sem dados</td></tr>':
                meses.map(m=>{const d=hist[m];return `<tr>
                    <td style="font-weight:600">${m}</td>
                    <td style="color:var(--entrada)">${fmtMoeda(d.entrada)}</td>
                    <td style="color:var(--saida)">${fmtMoeda(d.saida)}</td>
                    <td style="color:${d.saldo>=0?'var(--entrada)':'var(--saida)'};font-weight:700">${fmtMoeda(d.saldo)}</td>
                    <td>${d.transacoes}</td>
                    </tr>`;}).join('')}
                    </tbody></table>
                    </div>`;
}

// ==================== CHAT IA ====================
async function carregarModeloInfo(){
    const r=await api('/api/agente/modelo');
    document.getElementById('modelo-info').textContent=r.modelo?'Modelo: '+r.modelo:'⚠️ Nenhum modelo';
}

function adicionarMsgChat(texto,tipo='bot',isHtml=false){
    const div=document.getElementById('chat-msgs');
    const msg=document.createElement('div');
    msg.className='chat-msg '+tipo;
    msg.innerHTML=`${tipo==='bot'?'<div class="chat-avatar">🤖</div>':''}
    <div class="chat-bubble">${isHtml?texto:escHTML(texto)}</div>
    ${tipo==='user'?'<div class="chat-avatar">👤</div>':''}`;
    div.appendChild(msg);div.scrollTop=div.scrollHeight;
}

async function enviarChat(){
    const input=document.getElementById('chat-input');
    const msg=input.value.trim();
    if(!msg)return;
    adicionarMsgChat(msg,'user');
    input.value='';input.style.height='auto';
    const loadId='load-'+Date.now();
    const div=document.getElementById('chat-msgs');
    const ld=document.createElement('div');
    ld.className='chat-msg bot';ld.id=loadId;
    ld.innerHTML='<div class="chat-avatar">🤖</div><div class="chat-bubble"><div class="loading"></div></div>';
    div.appendChild(ld);div.scrollTop=div.scrollHeight;
    const r=await api('/api/agente/chat',{method:'POST',body:{mensagem:msg}});
    document.getElementById(loadId)?.remove();
    if(r.erro){adicionarMsgChat('Erro: '+r.erro,'bot');return;}
    try{
        const dados=JSON.parse(r.resposta||'');
        if(dados.tipo==='transacao_detectada'){
            const d=dados.dados;
            adicionarMsgChat(escHTML(dados.mensagem)+
            `<br><div style="margin-top:8px;display:flex;gap:8px">
            <button class="btn btn-success btn-sm"
            onclick="confirmarTransacaoChat(${JSON.stringify(d).replace(/"/g,'&quot;')})">✓ Confirmar</button>
            <button class="btn btn-ghost btn-sm"
            onclick="this.closest('.chat-bubble').innerHTML='<em style=color:var(--text-muted)>Cancelado</em>'">✗ Cancelar</button>
            </div>`,'bot',true);return;
        }
    }catch(e){}
    adicionarMsgChat(r.resposta||'Sem resposta','bot');
}

async function confirmarTransacaoChat(dados){
    const cat=E.categorias.find(c=>c.nome.toLowerCase()===(dados.categoria_sugerida||'').toLowerCase());
    const r=await api('/api/transacoes',{method:'POST',body:{
        tipo:dados.tipo||'saida',valor:dados.valor||0,
        nome_fantasia:dados.nome_fantasia||'Transação via Chat',
        descricao:dados.descricao||'',categoria_id:cat?.id||null,
        data:dados.data||new Date().toISOString().split('T')[0],origem:'agente'
    }});
    if(r.sucesso){toast('Transação registrada!','success');adicionarMsgChat('✅ Registrado!','bot');carregarDashboard();}
    else adicionarMsgChat('❌ Erro: '+r.erro,'bot');
}

// ==================== IA ====================
async function abrirAnaliseRapida(){
    document.getElementById('analise-title').textContent='🤖 Análise IA Completa';
    abrirModal('modal-analise');
    document.getElementById('analise-content').innerHTML=
    '<div style="text-align:center;padding:40px"><div class="loading" style="width:32px;height:32px;border-width:3px;margin:0 auto 12px"></div>Analisando...</div>';
    const r=await api('/api/agente/analise-completa');
    if(r.erro){document.getElementById('analise-content').innerHTML=`<div class="alert alert-error" style="display:block">${escHTML(r.erro)}</div>`;return;}
    const tend=r.tendencia||{};const anoms=r.anomalias||[];const projs=r.projecoes||[];
    document.getElementById('analise-content').innerHTML=`
    <div style="display:flex;flex-direction:column;gap:16px">
    ${(tend.alertas||[]).map(a=>`<div class="alerta-anomalia">${escHTML(a)}</div>`).join('')}
    <div class="analise-card">
    <div class="analise-title">📊 Resumo</div>
    <div class="analise-item"><span>Tendência Gastos</span><strong>${tend.tendencia_gastos||'—'}</strong></div>
    <div class="analise-item"><span>Variação</span><strong>${tend.variacao_gastos_pct||0}%</strong></div>
    <div class="analise-item"><span>Tendência Receitas</span><strong>${tend.tendencia_receitas||'—'}</strong></div>
    </div>
    ${anoms.length?`<div class="analise-card">
        <div class="analise-title">⚠️ Anomalias (${anoms.length})</div>
        ${anoms.map(a=>`<div class="analise-item">
            <span>${escHTML(a.nome_fantasia||'—')} (${a.tipo})</span>
            <span style="color:${a.severidade==='alta'?'var(--danger)':'var(--warning)'}">
            ${fmtMoeda(a.valor)} — ${a.severidade}</span>
            </div>`).join('')}
            </div>`:''}
            ${projs.length?`<div class="analise-card">
                <div class="analise-title">🔮 Próximo Mês</div>
                <div class="analise-item"><span>Entrada Est.</span><strong style="color:var(--entrada)">${fmtMoeda(projs[0]?.entrada)}</strong></div>
                <div class="analise-item"><span>Saída Est.</span><strong style="color:var(--saida)">${fmtMoeda(projs[0]?.saida)}</strong></div>
                <div class="analise-item"><span>Saldo Est.</span>
                <strong style="color:${(projs[0]?.saldo||0)>=0?'var(--entrada)':'var(--saida)'}">
                ${fmtMoeda(projs[0]?.saldo)}</strong></div>
                </div>`:''}
                </div>`;
}

async function abrirAnaliseTransacao(id){
    const t=E.transacoes.find(x=>x.id===id);if(!t)return;
    document.getElementById('analise-title').textContent='🤖 '+t.nome_fantasia;
    abrirModal('modal-analise');
    document.getElementById('analise-content').innerHTML=
    '<div style="text-align:center;padding:40px"><div class="loading" style="width:32px;height:32px;border-width:3px;margin:0 auto 12px"></div>Analisando...</div>';
    const r=await api('/api/agente/analisar-transacao/'+id);
    document.getElementById('analise-content').innerHTML=`
    <div class="analise-card">
    <div class="analise-title">🤖 ${escHTML(t.nome_fantasia)}</div>
    <div class="analise-item"><span>Valor</span>
    <strong style="color:${t.tipo==='entrada'?'var(--entrada)':'var(--saida)'}">
    ${t.tipo==='entrada'?'+':'-'}${fmtMoeda(t.valor)}</strong></div>
    <div class="analise-item"><span>Data</span><strong>${fmtData(t.data)}</strong></div>
    <div class="analise-item"><span>Anomalia</span>
    <strong style="color:${r.anormal?'var(--warning)':'var(--success)'}">
    ${r.anormal?'⚠️ Detectada':'✅ Normal'}</strong></div>
    ${r.resumo?`<div class="analise-item"><span>Análise</span><span>${escHTML(r.resumo)}</span></div>`:''}
    ${r.sugestao?`<div class="analise-item"><span>Sugestão</span><span style="color:var(--accent)">${escHTML(r.sugestao)}</span></div>`:''}
    </div>`;
}

// ==================== PDF ====================
function abrirModalImportarPDF(){
    document.getElementById('pdf-resultado').innerHTML='';
    document.getElementById('pdf-alert').style.display='none';
    document.getElementById('pdf-progress').style.display='none';
    document.getElementById('pdf-file').value='';
    abrirModal('modal-pdf');
}

async function importarPDF(){
    const file=document.getElementById('pdf-file').files[0];
    if(!file){mostrarAlert('pdf-alert','Selecione um arquivo PDF');return;}
    document.getElementById('pdf-progress').style.display='block';
    document.getElementById('btn-import-pdf').disabled=true;
    const fd=new FormData();fd.append('arquivo',file);
    const r=await apiForm('/api/extrato/pdf',fd);
    document.getElementById('pdf-progress').style.display='none';
    document.getElementById('btn-import-pdf').disabled=false;
    if(r.erro){mostrarAlert('pdf-alert',r.erro);return;}
    const trans=r.transacoes||[];
    if(!trans.length){mostrarAlert('pdf-alert','Nenhuma transação encontrada');return;}
    const entradas=trans.filter(t=>t.tipo==='entrada');
    const saidas=trans.filter(t=>t.tipo==='saida');
    document.getElementById('pdf-resultado').innerHTML=`
    <div style="margin-top:16px">
    <div style="display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap">
    <span style="color:var(--entrada)">✅ ${entradas.length} entradas</span>
    <span style="color:var(--saida)">❌ ${saidas.length} saídas</span>
    <span style="color:var(--text-muted)">${trans.length} total</span>
    ${r.duplicatas_ignoradas?`<span style="color:var(--warning)">⚠️ ${r.duplicatas_ignoradas} duplicatas ignoradas</span>`:''}
    </div>
    <div style="max-height:250px;overflow-y:auto;background:var(--bg-tertiary);
    border-radius:var(--radius);padding:8px;border:1px solid var(--border)">
    ${trans.slice(0,30).map(t=>`
        <div style="display:flex;justify-content:space-between;align-items:center;
        padding:6px 8px;border-bottom:1px solid var(--border);font-size:12px">
        <div><span style="color:var(--text-muted)">${fmtData(t.data)}</span>
        <span style="margin-left:8px">${escHTML(t.nome_fantasia)}</span></div>
        <span style="color:${t.tipo==='entrada'?'var(--entrada)':'var(--saida)'};font-weight:600;white-space:nowrap">
        ${t.tipo==='entrada'?'+':'-'}${fmtMoeda(t.valor)}</span>
        </div>`).join('')}
        ${trans.length>30?`<p style="text-align:center;padding:8px;color:var(--text-muted);font-size:12px">+${trans.length-30} mais...</p>`:''}
        </div>
        <button class="btn btn-success btn-full" style="margin-top:12px"
        onclick='confirmarImportacaoPDF(${JSON.stringify(trans).replace(/'/g,"&#39;")})'>
        ✓ Importar ${trans.length} transações
        </button>
        </div>`;
}

async function confirmarImportacaoPDF(transacoes){
    const r=await api('/api/extrato/importar',{method:'POST',body:{transacoes}});
    if(r.sucesso){
        let msg=`${r.importadas} transações importadas!`;
        if(r.duplicatas) msg+=` (${r.duplicatas} duplicatas ignoradas)`;
        toast(msg,'success');
        fecharModal('modal-pdf');
        carregarDashboard();
        if(E.paginaAtual==='transacoes') carregarTransacoes();
    } else toast(r.erro||'Erro','error');
}

// ==================== ADMIN ====================
async function carregarAdminUsuarios(){
    const r=await api('/api/admin/usuarios');
    const users=r.usuarios||[];
    document.getElementById('admin-usuarios-content').innerHTML=`
    <div class="table-container">
    <div class="table-header"><span style="font-weight:600">${users.length} usuários</span></div>
    <table><thead><tr>
    <th>Usuário</th><th>Perfil</th><th>Status</th>
    <th>Criado</th><th>Último Acesso</th><th>Ações</th>
    </tr></thead><tbody>
    ${users.map(u=>`<tr>
        <td><strong>${escHTML(u.username)}</strong></td>
        <td>${u.is_admin?'<span class="badge badge-quit">ADMIN</span>':'<span class="badge badge-org">Usuário</span>'}</td>
        <td>${u.suspenso?'<span class="badge badge-saida">Suspenso</span>':'<span class="badge badge-entrada">Ativo</span>'}</td>
        <td style="font-size:12px;color:var(--text-muted)">${u.criado_em?u.criado_em.split('T')[0]:'-'}</td>
        <td style="font-size:12px;color:var(--text-muted)">${u.ultimo_acesso?u.ultimo_acesso.split('T')[0]:'Nunca'}</td>
        <td><div style="display:flex;gap:4px">
        ${!u.is_admin?`
            <button class="btn btn-sm ${u.suspenso?'btn-success':'btn-warning'}"
            onclick="toggleSuspender('${u.user_id}',${!u.suspenso})">
            ${u.suspenso?'Reativar':'Suspender'}</button>
            <button class="btn btn-danger btn-sm"
            onclick="excluirUsuarioAdmin('${u.user_id}','${escHTML(u.username)}')">Excluir</button>
            `:'<span style="color:var(--text-muted);font-size:12px">—</span>'}
            </div></td>
            </tr>`).join('')}
            </tbody></table>
            </div>`;
}

async function toggleSuspender(uid,suspender){
    const r=await api('/api/admin/usuarios/'+uid+'/suspender',{method:'POST',body:{suspender}});
    if(r.sucesso){toast(suspender?'Suspenso':'Reativado','success');carregarAdminUsuarios();}
    else toast(r.erro||'Erro','error');
}

async function excluirUsuarioAdmin(uid,username){
    if(!confirm(`Excluir "${username}" e TODOS seus dados?`))return;
    const r=await api('/api/admin/usuarios/'+uid,{method:'DELETE'});
    if(r.sucesso){toast('Usuário excluído','success');carregarAdminUsuarios();}
    else toast(r.erro||'Erro','error');
}

async function carregarAdminSistema(){
    const r=await api('/api/admin/estatisticas');
    document.getElementById('admin-sistema-content').innerHTML=`
    <div class="cards-grid">
    <div class="card"><div class="card-label">Total Usuários</div><div class="card-value">${r.total_usuarios||0}</div></div>
    <div class="card"><div class="card-label">Ativos</div><div class="card-value" style="color:var(--success)">${r.usuarios_ativos||0}</div></div>
    <div class="card"><div class="card-label">Suspensos</div><div class="card-value" style="color:var(--danger)">${r.usuarios_suspensos||0}</div></div>
    <div class="card"><div class="card-label">Erros Pendentes</div><div class="card-value" style="color:var(--warning)">${r.erros_pendentes||0}</div></div>
    </div>
    <div class="analise-card">
    <div class="analise-title">Sistema</div>
    <div class="analise-item"><span>Modelo IA</span><strong>${r.modelo_ia_atual||'Não configurado'}</strong></div>
    </div>`;
}

async function carregarAdminLogs(){
    const r=await api('/api/admin/logs');
    const logs=r.logs||[];
    document.getElementById('admin-logs-content').innerHTML=!logs.length
    ?`<div class="empty-state"><div class="empty-icon">✅</div><div class="empty-title">Nenhum erro registrado</div></div>`
    :`<div class="table-container">
    <div class="table-header"><span style="font-weight:600">${logs.length} erros</span></div>
    <table><thead><tr><th>Data</th><th>Módulo</th><th>Erro</th><th>Ação</th></tr></thead>
    <tbody>${logs.map(l=>`<tr>
        <td style="font-size:11px;color:var(--text-muted)">${l.data?l.data.split('T')[0]:'-'}</td>
        <td><span class="badge badge-org">${escHTML(l.modulo)}</span></td>
        <td style="max-width:300px;font-size:12px">${escHTML(l.erro)}</td>
        <td>${!l.resolvido?`<button class="btn btn-success btn-sm"
            onclick="marcarLogResolvido('${l.id}')">✓ Resolvido</button>`:''}
            </td>
            </tr>`).join('')}</tbody></table>
            </div>`;
}

async function marcarLogResolvido(logId){
    const r=await api('/api/admin/logs/'+logId+'/resolver',{method:'POST'});
    if(r.sucesso){toast('Log resolvido','success');carregarAdminLogs();}
}

async function carregarAdminModelos(){
    const r=await api('/api/agente/modelos');
    const modelos=r.modelos||[];const atual=r.modelo_atual||null;
    document.getElementById('admin-modelos-content').innerHTML=`
    <div class="analise-card">
    <div class="analise-title">🤖 Modelos Ollama (172.17.0.1:11434)</div>
    ${!modelos.length?'<p style="color:var(--text-muted)">Nenhum modelo encontrado.</p>':
        modelos.map(m=>`<div style="display:flex;align-items:center;justify-content:space-between;
        padding:10px;background:var(--bg-tertiary);border-radius:var(--radius);margin-bottom:8px">
        <span style="font-family:monospace">${escHTML(m)}</span>
        ${m===atual?'<span class="badge badge-entrada">✓ Ativo</span>':
            `<button class="btn btn-primary btn-sm" onclick="selecionarModelo('${escHTML(m)}')">Selecionar</button>`}
            </div>`).join('')}
            <button class="btn btn-ghost btn-sm" style="margin-top:8px" onclick="carregarAdminModelos()">↻ Recarregar</button>
            </div>`;
}

async function selecionarModelo(nome){
    const r=await api('/api/agente/modelo',{method:'POST',body:{modelo:nome}});
    if(r.sucesso){toast('Modelo ativado: '+nome,'success');carregarAdminModelos();}
}

function renderizarAdminBackup(){
    document.getElementById('admin-backup-content').innerHTML=`
    <div class="analise-card">
    <div class="analise-title">💾 Exportar Backup</div>
    <p style="color:var(--text-secondary);margin-bottom:16px;font-size:13px">
    Dados exportados permanecem criptografados. Apenas o usuário com sua senha pode acessá-los.</p>
    <button class="btn btn-primary" onclick="exportarBackup()">📦 Exportar Backup</button>
    </div>
    <div class="analise-card" style="margin-top:16px">
    <div class="analise-title">📂 Importar Backup</div>
    <input type="file" id="import-file" accept=".zip" style="display:none" onchange="importarBackup(this)">
    <button class="btn btn-ghost" onclick="document.getElementById('import-file').click()">📂 Selecionar Backup (.zip)</button>
    </div>`;
}

async function exportarBackup(){
    toast('Gerando backup...','info');
    try{
        const r=await fetch('/api/admin/exportar',{headers:{'Authorization':'Bearer '+E.token,'X-Chave-Sessao':E.chaveSession}});
        if(!r.ok){toast('Erro','error');return;}
        const blob=await r.blob();
        const url=URL.createObjectURL(blob);
        const a=document.createElement('a');a.href=url;
        a.download='backup_'+new Date().toISOString().split('T')[0]+'.zip';
        a.click();URL.revokeObjectURL(url);
        toast('Backup exportado!','success');
    }catch(e){toast('Erro: '+e.message,'error');}
}

async function importarBackup(input){
    const file=input.files[0];if(!file)return;
    if(!confirm('Sobrescrever dados existentes?'))return;
    const fd=new FormData();fd.append('arquivo',file);
    toast('Importando...','info');
    const r=await apiForm('/api/admin/importar',fd);
    if(r.sucesso)toast('Importado!','success');else toast(r.erro||'Erro','error');
}

// ==================== SENHA ====================
function abrirModalSenha(){
    ['s-atual','s-nova','s-conf'].forEach(id=>document.getElementById(id).value='');
    document.getElementById('s-alert').style.display='none';
    abrirModal('modal-senha');
}

async function alterarSenha(){
    const atual=document.getElementById('s-atual').value;
    const nova=document.getElementById('s-nova').value;
    const conf=document.getElementById('s-conf').value;
    if(!atual||!nova||!conf){mostrarAlert('s-alert','Preencha todos os campos');return;}
    if(nova!==conf){mostrarAlert('s-alert','Senhas não coincidem');return;}
    if(nova.length<8){mostrarAlert('s-alert','Mínimo 8 caracteres');return;}
    const r=await api('/api/usuario/senha',{method:'PUT',body:{senha_atual:atual,nova_senha:nova}});
    if(r.erro){mostrarAlert('s-alert',r.erro);return;}
    toast('Senha alterada! Faça login novamente.','success');
    document.getElementById('aviso-senha').style.display='none';
    fecharModal('modal-senha');
    setTimeout(()=>logout(),2000);
}

// Init
document.getElementById('mt-data').value=new Date().toISOString().split('T')[0];
