/** Small standalone Home Assistant panel for Cisco Catalyst VLAN creation. */
const VLAN_PANEL_VERSION = "0.1.4";
const isDeletableVlanId = id => Number.isInteger(id) && id >= 2 && id <= 1001;
const shortInterfaceName=name=>name.replace(/^(GigabitEthernet|TenGigabitEthernet|FortyGigabitEthernet|TwentyFiveGigE)(?=\d)/,prefix=>({GigabitEthernet:"Gi",TenGigabitEthernet:"Te",FortyGigabitEthernet:"Fo",TwentyFiveGigE:"Twe"})[prefix]);
class CiscoCatalystVlanPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._ready=false;
    this._busy=false;
    this._message="";
    this._entryId="";
    this._switchName="";
    this._vlanNames=new Map();
    this._protectedVlans=new Set();
    this._portsByVlan=null;
    this._detailsVlan=null;
    this._refreshing=null;
    this._lastEntitySignature="";
    this._filter="";
    this._page=0;
    this._pageSize=25;
    this._deletePortCount=null;
  }
  set hass(hass) {
    this._hass=hass;
    if (!this._ready && !this._loading) this.load();
    else if (this._ready) {
      const signature=Object.entries(hass.states||{}).filter(([id])=>id.startsWith("select.")&&id.endsWith("_access_vlan")).map(([id,v])=>id+":"+v.state).sort().join("|");
      if(signature!==this._lastEntitySignature){
        this._lastEntitySignature=signature;
        this.refreshPortOverview();
      }
    }
  }
  set panel(value) { this._panel=value; }
  async load() {
    this._loading=true;
    try {
      const devices=await this._hass.callWS({type:"config/device_registry/list"});
      const candidates=devices.filter(d=>Array.isArray(d.identifiers)&&d.identifiers.some(i=>i[0]==="cisco_catalyst")&&Array.isArray(d.config_entries)&&d.config_entries.length);
      const switches=candidates.filter(d=>!(d.via_device_id||d.parent_device_id));
      if (switches.length!==1) throw Error("Expected one Cisco Catalyst parent switch; found "+switches.length);
      this._entryId=switches[0].config_entries[0];
      this._switchName=switches[0].name_by_user||switches[0].name||"Cisco Catalyst";
      this._ready=true;
      this.render();
      await this.loadInventoryNames();
      await this.loadProtectionSettings();
    } catch(e) { this.shadowRoot.textContent="VLAN panel setup: "+(e.message||e); }
    finally { this._loading=false; }
  }
  async loadInventoryNames() {
    try {
      const result=await this._hass.callService("cisco_catalyst","list_vlans",
        {entry_id:this._entryId},undefined,false,true);
      const rows=result?.response?.vlans;
      if(!Array.isArray(rows))throw Error("VLAN inventory response unavailable");
      this._vlanNames=new Map(rows.filter(row=>Number.isInteger(row.id)).map(row=>[row.id,row.name||""]));
      this.updateOrphanedPorts();
      await this.loadPortOverview();
      this.updateStandaloneChoices();
      this.shadowRoot.getElementById("inventory")?.removeAttribute("data-signature");
      this.updateInventory();
      const picker=this.shadowRoot.getElementById("rename-vlan");
      const deletePicker=this.shadowRoot.getElementById("delete-vlan");
      const destination=this.shadowRoot.getElementById("destination-vlan");
      if(deletePicker){
        const previouslySelected=deletePicker.value;
        deletePicker.replaceChildren();
        destination.replaceChildren();
        for(const [id,name] of [...this._vlanNames].sort((a,b)=>a[0]-b[0])){
          const label=id+" — "+name;
          if(isDeletableVlanId(id)&&!this._protectedVlans.has(id))deletePicker.add(new Option(label,String(id)));
          if(id>=1 && id<=1001&&!this._protectedVlans.has(id))destination.add(new Option(label,String(id)));
        }
        // A deleted (or unselected) VLAN must not silently become the first option.
        if(previouslySelected && [...deletePicker.options].some(option=>option.value===previouslySelected))
          deletePicker.value=previouslySelected;
        else deletePicker.selectedIndex=-1;
        this.updateDeleteConfirmationHint();
      }
      if(deletePicker?.value&&!this.shadowRoot.getElementById("delete-section").hidden)await this.previewDelete();
      if(picker){
        const selected=picker.value;
        picker.replaceChildren();
        for(const [id,name] of [...this._vlanNames].sort((a,b)=>a[0]-b[0])){
          if(id<2||id>1001||this._protectedVlans.has(id))continue;
          const option=document.createElement("option");
          option.value=String(id);
          option.textContent=id+" — "+name;
          picker.append(option);
        }
        if([...picker.options].some(o=>o.value===selected))picker.value=selected;
      }
    } catch(e) {
      const status=this.shadowRoot.getElementById("status");
      if(status && !status.textContent)status.textContent="VLAN names unavailable: "+(e.message||e);
    }
  }
  async refreshPortOverview() {
    if(this._refreshing)return this._refreshing;
    this._refreshing=(async()=>{
      await this.loadPortOverview();
      this.shadowRoot.getElementById("inventory")?.removeAttribute("data-signature");
      this.updateInventory();
      if(this._detailsVlan!==null&&!this.shadowRoot.getElementById("details-section").hidden)
        this.showVlanDetails(this._detailsVlan,false);
    })();
    try { await this._refreshing; } finally { this._refreshing=null; }
  }
  async loadPortOverview() {
    try {
      const response=await this._hass.callService("cisco_catalyst","vlan_port_overview",
        {entry_id:this._entryId},undefined,false,true);
      const groups=response?.response?.ports_by_vlan;
      if(!groups||typeof groups!=="object")throw Error("Port overview unavailable");
      this._portsByVlan=groups;
      this.updateOrphanedPorts();
      const indicator=this.shadowRoot.getElementById("ports-updated");
      if(indicator)indicator.textContent="Panel checked "+new Date().toLocaleTimeString()+" · last HA polling snapshot (not a fresh switch read)";
    } catch(e) {
      this._portsByVlan=null;
      const indicator=this.shadowRoot.getElementById("ports-updated");
      if(indicator)indicator.textContent="Port overview unavailable";
    }
  }
  updateOrphanedPorts() {
    const node=this.shadowRoot.getElementById("orphaned-ports");
    if(!node)return;
    node.replaceChildren();
    const orphaned=Object.entries(this._portsByVlan||{}).filter(([id])=>!this._vlanNames.has(Number(id)));
    if(!orphaned.length){node.textContent="No inactive access VLAN assignments in the latest HA snapshot.";return;}
    const title=document.createElement("strong");
    title.textContent="Inactive VLAN assignments — attention required";
    node.append(title);
    for(const [id,ports] of orphaned){
      const row=document.createElement("p");
      row.textContent="VLAN "+id+" (not operational): "+ports.map(p=>shortInterfaceName(p.name)).join(", ");
      node.append(row);
      for(const port of ports){
        const button=document.createElement("button");
        button.textContent="Review recovery: "+shortInterfaceName(port.name);
        button.type="button";
        button.addEventListener("click",()=>this.openRecovery(port,Number(id)));
        node.append(button);
      }
    }
    const note=document.createElement("small");
    note.textContent="Cached observation only. No recovery or switch changes are performed here.";
    node.append(note);
  }
  showOnlyWorkflow(active) {
    for(const id of ["recovery","move","create","rename","delete","details"]){
      this.shadowRoot.getElementById(id+"-section").hidden=id!==active;
    }
    if(active!=="recovery"){
      this._recoveryPort=null;
      this.shadowRoot.getElementById("recovery-confirm").value="";
    }
    if(active!=="details")this._detailsVlan=null;
  }
  openRecovery(port,source){
    this.showOnlyWorkflow("recovery");
    this._recoveryPort={...port,source};
    const section=this.shadowRoot.getElementById("recovery-section");
    const select=this.shadowRoot.getElementById("recovery-target");
    select.replaceChildren();
    for(const [id,name] of [...this._vlanNames].sort((a,b)=>a[0]-b[0])){
      if(id>=1 && id<=1001 && !this._protectedVlans.has(id))
        select.add(new Option(id+" — "+name,String(id)));
    }
    this.shadowRoot.getElementById("recovery-port").textContent=
      shortInterfaceName(port.name)+" — VLAN "+source+" is inactive (cached snapshot)";
    this.shadowRoot.getElementById("recovery-confirm").value="";
    this.updateRecoveryPhrase();
    this.shadowRoot.getElementById("recovery-message").textContent=
      "No switch change yet. Confirm the exact port and destination before submitting.";
    section.hidden=false;
    section.scrollIntoView({block:"nearest"});
  }
  updateRecoveryPhrase(){
    const port=this._recoveryPort;
    const target=this.shadowRoot.getElementById("recovery-target").value;
    const phrase=port && target ? "RECOVER TO "+target : "";
    this.shadowRoot.getElementById("recovery-confirm").placeholder=phrase||"RECOVER TO <VLAN ID>";
    this.shadowRoot.getElementById("recovery-confirm").value="";
  }
  async submitRecovery(event){
    event.preventDefault();
    const port=this._recoveryPort;
    if(!port)return;
    const target=Number(this.shadowRoot.getElementById("recovery-target").value);
    const confirmation=this.shadowRoot.getElementById("recovery-confirm").value.trim();
    const expected="RECOVER TO "+target;
    const status=this.shadowRoot.getElementById("recovery-message");
    if(confirmation!==expected){status.textContent="Enter exactly: "+expected;return;}
    const button=event.target.querySelector('button[type="submit"]');
    button.disabled=true;
    try{
      const result=await this._hass.callService("cisco_catalyst","recover_orphaned_access_port",{
        entry_id:this._entryId,if_index:port.if_index,expected_interface_name:port.name,
        source_vlan:port.source,destination_vlan:target,confirmation
      },undefined,true,true);
      const response=result?.response??result;
      status.textContent=response?.status==="verified"
        ?"Recovery verified on VLAN "+response.readback_vlan+"."
        :"Recovery not verified. Inspect the switch before retrying.";
      if(response?.status==="verified"){
        await this.loadInventoryNames();
        this._recoveryPort=null;
        this.shadowRoot.getElementById("recovery-confirm").value="";
        this.shadowRoot.getElementById("recovery-section").hidden=true;
        this.shadowRoot.getElementById("inventory-status").textContent="Recovery verified on VLAN "+response.readback_vlan+".";
      }
    }catch(error){status.textContent="Recovery failed or is uncertain: "+(error.message||error)+". Inspect switch state before retrying.";}
    finally{button.disabled=false;}
  }
  showVlanDetails(vlan,scroll=true) {
    this._detailsVlan=vlan;
    this.showOnlyWorkflow("details");
    const section=this.shadowRoot.getElementById("details-section");
    section.hidden=false;
    const title=this.shadowRoot.getElementById("details-title");
    title.textContent="VLAN "+vlan+" — "+(this._vlanNames.get(vlan)||"")+" · Ports";
    const body=this.shadowRoot.getElementById("details-ports");
    body.replaceChildren();
    if(!this._portsByVlan) {
      body.textContent="Port count unavailable. Refresh the panel to try again.";
    } else {
      const ports=this._portsByVlan[String(vlan)]||[];
      const summary=document.createElement("p");
      summary.textContent=ports.length+" detected access ports. Last polling snapshot, not a fresh switch read. Trunk memberships excluded.";
      body.append(summary);
      const table=document.createElement("div");
      table.className="details-table";
      const header=document.createElement("div");
      header.className="details-row details-heading";
      for(const heading of ["Port","Link","PoE","Description"]){
        const cell=document.createElement("strong");cell.textContent=heading;header.append(cell);
      }
      table.append(header);
      const state=(value,kind)=>{
        const cell=document.createElement("span");
        const states=kind==="link"?{
          up:["↑","Up","good"],down:["↓","Down","bad"]
        }:{
          powering:["⚡","Powering","good"],idle:["○","Idle","neutral"],
          enabled:["⚡","Enabled","neutral"],disabled:["⊘","Disabled","bad"],
          unavailable:["—","Unavailable","neutral"]
        };
        const parts=states[value]||["?","Unknown","neutral"];
        const icon=document.createElement("span");
        icon.className="state-symbol "+parts[2];
        icon.textContent=parts[0];icon.setAttribute("aria-hidden","true");
        cell.append(icon,document.createTextNode(" "+parts[1]));
        cell.setAttribute("aria-label",kind+" "+parts[1]);
        return cell;
      };
      for(const port of [...ports].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}))){
        const line=document.createElement("div");line.className="details-row";
        const name=document.createElement("strong");name.textContent=shortInterfaceName(port.name);
        name.title=port.name;
        const description=document.createElement("span");
        description.textContent=port.description||"No description";
        line.append(name,state(port.link,"link"),state(port.poe,"poe"),description);
        table.append(line);
      }
      body.append(table);
    }
    if(scroll)section.scrollIntoView({block:"nearest"});
  }
  inventory() {
    const found=new Set();
    for (const [id,state] of Object.entries(this._hass?.states||{})) {
      if (!id.startsWith("select.")||!id.endsWith("_access_vlan")) continue;
      for (const option of state.attributes?.options||[]) {
        const n=Number(option);
        if(Number.isInteger(n)&&n>=1&&n<=4094)found.add(n);
      }
    }
    return [...found].sort((a,b)=>a-b);
  }
  updateInventory() {
    const node=this.shadowRoot.getElementById("inventory");
    if (!node)return;
    const vlans=this._vlanNames.size?[...this._vlanNames.keys()].sort((a,b)=>a-b):this.inventory();
    const matches=vlans.filter(id=>(id+" "+(this._vlanNames.get(id)||"")).toLowerCase().includes(this._filter.toLowerCase()));
    const pageCount=Math.max(1,Math.ceil(matches.length/this._pageSize));
    this._page=Math.min(this._page,pageCount-1);
    const shown=matches.slice(this._page*this._pageSize,(this._page+1)*this._pageSize);
    const info=this.shadowRoot.getElementById("page-info");
    if(info)info.textContent=matches.length+" VLANs · Page "+(this._page+1)+" of "+pageCount;
    const prev=this.shadowRoot.getElementById("prev-page"),next=this.shadowRoot.getElementById("next-page");
    if(prev)prev.disabled=this._page===0;
    if(next)next.disabled=this._page>=pageCount-1;
    const signature=this._filter+":"+this._page+":"+this._pageSize+"|"+shown.map(id=>id+":"+(this._vlanNames.get(id)||"")+":"+this._protectedVlans.has(id)+":"+(this._portsByVlan?.[String(id)]?.length??"?")).join(",");
    if (node.dataset.signature===signature)return;
    node.dataset.signature=signature;
    node.replaceChildren();
    if (!shown.length) {
      node.textContent=vlans.length?"No matching VLANs.":"VLAN inventory unavailable.";
      return;
    }
    for (const vlan of shown) {
      const row=document.createElement("div");
      row.className="vlan-row";
      const identity=document.createElement("span");
      identity.textContent=vlan+" — "+(this._vlanNames.get(vlan)||"");
      const label=document.createElement("label");
      label.className="vlan-protection";
      const box=document.createElement("input");
      box.type="checkbox";
      box.checked=vlan===1||(vlan>=1002&&vlan<=1005)||this._protectedVlans.has(vlan);
      box.disabled=vlan===1||vlan>1001;
      box.setAttribute("aria-label","Protect VLAN "+vlan);
      box.addEventListener("change",()=>this.toggleProtection(vlan,box,actionButtons,saving));
      const saving=document.createElement("small");saving.textContent="Saving…";saving.hidden=true;
      label.append(box,document.createTextNode("Protected"),saving);
      const actionButtons=[];
      for(const action of ["rename","delete"]){
        const button=document.createElement("button");
        button.type="button";button.textContent=action==="rename"?"Rename":"Delete";
        button.disabled=!isDeletableVlanId(vlan)||this._protectedVlans.has(vlan);
        button.addEventListener("click",()=>this.openOperation(action,vlan));
        actionButtons.push(button);
      }
      const count=document.createElement("span");
      count.className="vlan-port-count";
      count.textContent=this._portsByVlan?String((this._portsByVlan[String(vlan)]||[]).length):"—";
      count.title="Detected access ports in last polling snapshot";
      const details=document.createElement("button");
      details.type="button";details.textContent="Details";
      details.addEventListener("click",()=>this.showVlanDetails(vlan));
      row.append(identity,...actionButtons,count,label,details);
      node.append(row);
    }
  }
  openOperation(action,vlan) {
    this.showOnlyWorkflow(action);
    if(action==="rename"){
      const form=this.shadowRoot.getElementById("rename");
      form.elements.vlan.value=String(vlan);
      this.shadowRoot.getElementById("rename-target").value=String(vlan);
      form.elements.name.value=this._vlanNames.get(vlan)||"";
      this.shadowRoot.getElementById("rename-status").textContent="";
    }
    if(action==="delete"){
      const deleteForm=this.shadowRoot.getElementById("delete");
      deleteForm.elements.confirmation.value="";
      this.shadowRoot.getElementById("delete-status").textContent="";
      this.shadowRoot.getElementById("delete-preview").textContent="Checking affected ports…";
      this.shadowRoot.getElementById("bulk-move-preview").textContent="";
      this.shadowRoot.getElementById("delete-vlan").value=String(vlan);
      this.shadowRoot.getElementById("delete-target").textContent=vlan+" — "+(this._vlanNames.get(vlan)||"");
      this.updateDeleteConfirmationHint();
      this.updateDestinationChoices();
      this.updateDeleteMode(null);
      this.previewDelete();
    }
    this.shadowRoot.getElementById(action+"-section").scrollIntoView({block:"nearest"});
  }
  async toggleProtection(vlan,box,buttons,saving) {
    const next=box.checked;
    const previouslyProtected=this._protectedVlans.has(vlan);
    box.disabled=true;
    saving.hidden=false;
    for(const button of buttons)button.disabled=true;
    const status=this.shadowRoot.getElementById("inventory-status");
    try {
      const result=await this._hass.callService("cisco_catalyst","set_vlan_protected",
        {entry_id:this._entryId,vlan_id:vlan,protected:next},undefined,false,true);
      if(result?.response?.status!=="saved")throw Error("Protection change not verified");
      if(next)this._protectedVlans.add(vlan);
      else this._protectedVlans.delete(vlan);
      status.textContent="VLAN "+vlan+" protection "+(next?"enabled":"disabled")+".";
      const form=this.shadowRoot.getElementById("protection-settings");
      form.elements.protected_vlans.value=[...this._protectedVlans].sort((a,b)=>a-b).join(", ");
      // Inventory refresh may fail after settings have already been saved.
      // Keep the confirmed protection state and report refresh failure separately.
      try{await this.loadInventoryNames();}
      catch(refreshError){status.textContent+=" Inventory refresh failed: "+(refreshError.message||refreshError);}
    }catch(e){
      box.checked=previouslyProtected;
      for(const button of buttons)button.disabled=previouslyProtected;
      status.textContent="VLAN "+vlan+" protection not saved: "+(e.message||e);
    }finally{box.disabled=false;saving.hidden=true;for(const button of buttons)button.disabled=this._protectedVlans.has(vlan);}
  }
  render() {
    this.shadowRoot.innerHTML=`
      <style>
        :host{display:block;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,Arial,sans-serif)}
        main{max-width:850px;margin:24px auto;padding:20px;background:var(--card-background-color,#fff);border-radius:12px}
        form{display:flex;flex-wrap:wrap;gap:12px;align-items:end}label{display:grid;gap:6px}label[hidden]{display:none!important}
        input{box-sizing:border-box;padding:10px;color:var(--primary-text-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:6px}
        button{padding:11px 17px;border:0;border-radius:6px;background:var(--primary-color);color:#fff;cursor:pointer}
        button:disabled{opacity:.35;cursor:not-allowed;background:var(--disabled-text-color,#777)}
        #create input:disabled,#rename input:disabled{opacity:.45;cursor:not-allowed;background:var(--secondary-background-color,#eee)}
        #rename-target:read-only{opacity:.7;background:var(--secondary-background-color,#eee)}#inventory{display:block;min-height:32px}.vlan-chip{display:inline-block;padding:4px 10px;border-radius:7px;background:var(--secondary-background-color,#eee);border:1px solid var(--divider-color,#ccc);font-variant-numeric:tabular-nums}
        select{padding:10px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);border-radius:6px}
        #rename-status{margin-top:12px;white-space:pre-line}
        .vlan-row{display:grid;grid-template-columns:minmax(0,1fr) 74px 69px 55px 116px 70px;align-items:center;gap:12px;padding:9px 12px;border-bottom:1px solid var(--divider-color)}
        .vlan-row>button{width:100%;min-width:0;box-sizing:border-box;text-align:center;padding:6px 4px}
        .vlan-protection{display:flex;align-items:center;gap:8px;white-space:nowrap}
        .vlan-protection input{width:auto}
        .vlan-actions{display:flex;justify-content:flex-start;gap:5px;flex-wrap:nowrap}.vlan-actions button{padding:6px 10px}
        .vlan-port-count{text-align:center;font-variant-numeric:tabular-nums}
        .move-port{display:flex;align-items:center;gap:8px;padding:5px 0}
        .move-port input{flex:none}
        .details-table{overflow-x:auto}
        .details-row{display:grid;grid-template-columns:120px 85px 115px minmax(170px,1fr);gap:12px;align-items:center;padding:9px 5px;border-bottom:1px solid var(--divider-color);min-width:540px}
        .details-heading{background:var(--secondary-background-color,#eee)}
        .details-row>span{overflow-wrap:anywhere}
        .state-symbol{font-weight:bold;font-size:18px}
        .state-symbol.good{color:#188038}.state-symbol.bad{color:#c62828}.state-symbol.neutral{color:var(--secondary-text-color,#777)}
        #delete{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
        #delete>p{margin:0;min-width:0;overflow-wrap:anywhere}
        #delete>label{min-width:0}
        #delete input[name="confirmation"],#delete select{max-width:100%;width:100%;min-width:0}
        #delete button[type="submit"]{justify-self:start}
        @media(max-width:650px){
          .vlan-row{grid-template-columns:minmax(0,1fr) 74px 65px 42px 94px 64px;gap:5px;padding:10px 3px;font-size:13px}
          .vlan-actions{grid-column:auto;justify-content:flex-start}
          .vlan-protection{gap:4px}.vlan-actions button{padding:7px 10px}
          #delete{grid-template-columns:minmax(0,1fr)}
        }
        .vlan-heading{font-weight:bold;font-size:12px;background:var(--secondary-background-color,#eee)}
        .vlan-heading span:nth-child(3){text-align:center}
        @media(max-width:550px){
          .vlan-row{grid-template-columns:minmax(0,1fr) 68px 112px;gap:5px}
          .vlan-row>span:first-child{grid-column:1;grid-row:1;overflow-wrap:anywhere}
          .vlan-row>button:nth-child(2){grid-column:1;grid-row:2;justify-self:start}
          .vlan-row>button:nth-child(3){grid-column:2;grid-row:2}
          .vlan-port-count{grid-column:2;grid-row:1}
          .vlan-port-count::before{content:"Ports: ";font-size:11px}
          .vlan-protection{grid-column:3;grid-row:1}
          .vlan-row>button:last-child{grid-column:3;grid-row:2}
          .vlan-heading{display:none}
        }
        .vlan-tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin:12px 0}
        .operation-section[hidden]{display:none}
        .operation-section{border:1px solid var(--divider-color,#ccc);border-radius:10px;padding:16px;margin:18px 0}
        .operation-section h2{margin-top:0}
        .name-rules{font-size:13px;opacity:.78;margin-top:10px}
        .panel-version{font-size:12px;opacity:.7;margin-top:-8px}
        #status{margin-top:12px;white-space:pre-line}
      </style>
      <main><h1>VLAN Management</h1><p id="switch"></p><p class="panel-version">Panel version: ${VLAN_PANEL_VERSION}</p>
        <section aria-label="Inactive VLAN assignments"><h2>Inactive VLAN assignments</h2><div id="orphaned-ports">Checking HA snapshot…</div></section><section class="operation-section" id="recovery-section" hidden><h2>Recover inactive VLAN assignment</h2><p id="recovery-port"></p><form id="recovery-form"><label>Destination VLAN<select id="recovery-target"></select></label><label>Confirmation (enter RECOVER TO followed by the destination VLAN ID)<input id="recovery-confirm" type="text" required autocomplete="off" placeholder="RECOVER TO <VLAN ID>"></label><button type="submit">Recover this port</button></form><p id="recovery-message" role="status"></p></section><div class="vlan-tools"><h2>Existing VLANs</h2><span><button type="button" id="move-open">Move ports</button> <button type="button" id="create-open">+ Create VLAN</button></span></div>
        <div class="vlan-tools"><button type="button" id="refresh-ports">Refresh ports</button><span id="ports-updated" style="font-size:12px"></span></div><div class="vlan-tools"><input id="vlan-search" type="search" placeholder="Search VLAN ID or name"><label>Rows <select id="page-size"><option>10</option><option selected>25</option><option>50</option><option>100</option></select></label></div>
        <div class="vlan-row vlan-heading"><span>VLAN</span><span>Rename</span><span>Delete</span><span>Ports</span><span>Protected</span><span>Details</span></div><div id="inventory"></div><div class="vlan-tools"><span id="page-info"></span><span><button id="prev-page" type="button">Previous</button> <button id="next-page" type="button">Next</button></span></div><div id="inventory-status" role="status" aria-live="polite"></div>
        <section class="operation-section" id="move-section" hidden><h2>Move access ports (without deleting VLAN)</h2>
          <form id="move-form">
            <label>Source VLAN<select id="move-source"></select></label>
            <label>Destination VLAN<select id="move-destination"></select></label>
            <div id="move-ports" style="width:100%"></div>
            <p id="move-confirm-hint" style="width:100%"></p>
            <label>Confirmation<input type="text" id="move-confirmation" autocomplete="off"></label>
            <button type="submit">Move selected ports</button>
          </form><div id="move-status" role="status" aria-live="polite"></div>
        </section>
        <section class="operation-section" id="details-section" hidden><h2 id="details-title">VLAN Details</h2><div id="details-ports"></div></section>
        <section class="operation-section" id="create-section" hidden><h2>Create VLAN</h2><form id="create">
          <label>VLAN ID<input name="vlan" type="number" min="2" max="1001" required></label>
          <label>VLAN name<input name="name" type="text" pattern="[A-Za-z0-9_-]+" maxlength="32" required placeholder="CAMERAS"></label>
          <button type="submit">Create VLAN</button>
        </form><p class="name-rules">Name: 1–32 letters, digits, underscores (_) or hyphens (-). No spaces or other punctuation.</p><div id="status" role="status" aria-live="polite"></div></section>
        <section class="operation-section" id="rename-section" hidden><h2>Rename VLAN</h2><form id="rename">
          <label>VLAN ID<input id="rename-target" type="number" readonly tabindex="-1"><select id="rename-vlan" name="vlan" required hidden></select></label>
          <label>VLAN name<input name="name" type="text" pattern="[A-Za-z0-9_-]+" maxlength="32" required placeholder="CAMERAS"></label>
          <button type="submit">Rename VLAN</button>
        </form><p class="name-rules">Name: 1–32 letters, digits, underscores (_) or hyphens (-). No spaces or other punctuation.</p><div id="rename-status" role="status" aria-live="polite"></div></section>
        <section class="operation-section" id="delete-section" hidden><h2>Delete VLAN</h2>
          <form id="delete">
            <label>VLAN <span id="delete-target"></span><select id="delete-vlan" name="vlan" required hidden></select></label>
            <p id="delete-preview">Checking affected ports…</p><p>Trunk, routed and VTP-domain dependencies may exist.</p>
            <p id="delete-mode-hint" role="status" aria-live="polite">Checking affected ports…</p>
            <label id="delete-destination-label" hidden>Move assigned ports to VLAN<select id="destination-vlan" name="destination"></select></label>
            <p>The Integration verifies live switch membership, moves eligible ports when necessary, then checks for remaining assignments before deleting. Inactive-VLAN recovery remains available.</p><p id="bulk-move-preview" role="status" aria-live="polite"></p>
            <label>Confirmation (enter DELETE followed by the VLAN ID)<input name="confirmation" type="text" required placeholder="DELETE 997"></label>
            <button type="submit">Delete VLAN</button>
          </form><div id="delete-status" role="status" aria-live="polite"></div>
        </section>
        <details class="operation-section" hidden><summary>VLAN Management Settings</summary>
        <form id="protection-settings">
        <label>Protected interfaces<textarea name="protected_interfaces" rows="3" style="width:min(100%,540px);min-width:280px;box-sizing:border-box;padding:10px;border:1px solid var(--divider-color);border-radius:6px;background:var(--card-background-color);color:var(--primary-text-color)"></textarea></label>
        <input type="hidden" name="protected_vlans">
        <button type="submit">Save protection settings</button></form>
        <p id="protection-status" role="status"></p></details>
      </main>`;
    this.shadowRoot.getElementById("switch").textContent=this._switchName;
    this.shadowRoot.getElementById("recovery-form").addEventListener("submit",e=>this.submitRecovery(e));
    this.shadowRoot.getElementById("recovery-target").addEventListener("change",()=>this.updateRecoveryPhrase());
    this.shadowRoot.getElementById("move-open").addEventListener("click",()=>{
      this.showOnlyWorkflow("move");
      const section=this.shadowRoot.getElementById("move-section");
      section.hidden=false;
      this.updateStandaloneChoices();this.previewStandaloneMove();
      section.scrollIntoView({block:"start",behavior:"smooth"});
    });
    for(const id of ["move-source","move-destination"])
      this.shadowRoot.getElementById(id).addEventListener("change",()=>this.previewStandaloneMove());
    this.shadowRoot.getElementById("move-ports").addEventListener("change",()=>this.updateMoveConfirmation());
    this.shadowRoot.getElementById("move-form").addEventListener("submit",e=>this.executeStandaloneMove(e));
    this.shadowRoot.getElementById("refresh-ports").addEventListener("click",()=>this.refreshPortOverview());
    this.shadowRoot.getElementById("create-open").addEventListener("click",()=>this.openOperation("create"));
    this.shadowRoot.getElementById("vlan-search").addEventListener("input",e=>{this._filter=e.target.value;this._page=0;this.updateInventory();});
    this.shadowRoot.getElementById("page-size").addEventListener("change",e=>{this._pageSize=Number(e.target.value);this._page=0;this.updateInventory();});
    this.shadowRoot.getElementById("prev-page").addEventListener("click",()=>{this._page--;this.updateInventory();});
    this.shadowRoot.getElementById("next-page").addEventListener("click",()=>{this._page++;this.updateInventory();});
    this.shadowRoot.getElementById("create").addEventListener("submit",e=>this.create(e));
    this.shadowRoot.getElementById("rename").addEventListener("submit",e=>this.rename(e));
    this.shadowRoot.getElementById("delete").addEventListener("submit",e=>this.deleteVlan(e));
    this.shadowRoot.getElementById("protection-settings").addEventListener("submit",e=>this.saveProtectionSettings(e));
    this.shadowRoot.getElementById("delete-vlan").addEventListener("change",()=>{this.updateDeleteConfirmationHint();this.updateDestinationChoices();this.updateDeleteMode(null);this.previewDelete();});
    this.shadowRoot.getElementById("destination-vlan").addEventListener("change",()=>this.previewBulkMove());
    this.updateInventory();
  }
  updateDestinationChoices() {
    const target=Number(this.shadowRoot.getElementById("delete-vlan")?.value);
    const destination=this.shadowRoot.getElementById("destination-vlan");
    if(!destination)return;
    const previous=destination.value;
    destination.replaceChildren();
    for(const [id,name] of [...this._vlanNames].sort((a,b)=>a[0]-b[0])){
      if(id<1||id>1001||id===target||this._protectedVlans.has(id))continue;
      destination.add(new Option(id+" — "+name,String(id)));
    }
    if([...destination.options].some(option=>option.value===previous))destination.value=previous;
    this.updateDeleteMode(this._deletePortCount);
  }
  updateDeleteMode(count) {
    this._deletePortCount=count;
    const label=this.shadowRoot.getElementById("delete-destination-label");
    const select=this.shadowRoot.getElementById("destination-vlan");
    const hint=this.shadowRoot.getElementById("delete-mode-hint");
    const submit=this.shadowRoot.querySelector('#delete button[type="submit"]');
    if(!label||!select||!hint)return;
    const needsMove=count!==null&&count>0;
    label.hidden=!needsMove;
    select.required=needsMove;
    hint.textContent=count===null?"Port membership preview unavailable; refresh before deleting.":
      needsMove?count+" detected access ports. Choose the destination VLAN; ports will be moved before deletion.":
      "No access ports detected. No destination needed; live switch membership will still be checked.";
    if(submit&&!this._busy)submit.disabled=count===null||(needsMove&&!select.options.length);
    if(!needsMove)this.shadowRoot.getElementById("bulk-move-preview").textContent="";
  }
  updateDeleteConfirmationHint() {
    const id=Number(this.shadowRoot.getElementById("delete-vlan")?.value);
    const input=this.shadowRoot.querySelector('#delete input[name="confirmation"]');
    if(input)input.placeholder=isDeletableVlanId(id)?"DELETE "+id:"DELETE <VLAN ID>";
  }
  async loadProtectionSettings() {
    const form=this.shadowRoot.getElementById("protection-settings");
    const status=this.shadowRoot.getElementById("protection-status");
    try {
      const result=await this._hass.callService("cisco_catalyst","get_vlan_protection",
        {entry_id:this._entryId},undefined,false,true);
      const value=result?.response;
      if(typeof value?.protected_interfaces!=="string"||typeof value?.protected_vlans!=="string")
        throw Error("Settings unavailable");
      form.elements.protected_interfaces.value=value.protected_interfaces.split(",").map(x=>x.trim()).filter(Boolean).join("\n");
      form.elements.protected_vlans.value=value.protected_vlans;
      this._protectedVlans=new Set(value.protected_vlans.split(",").map(x=>Number(x.trim())).filter(x=>Number.isInteger(x)&&x>0));
      this.shadowRoot.getElementById("inventory")?.removeAttribute("data-signature");
      this.updateInventory();
      await this.loadInventoryNames();
    }catch(e){status.textContent="Cannot read settings: "+(e.message||e);}
  }
  async saveProtectionSettings(event) {
    event.preventDefault();
    if(this._busy)return;
    const form=event.currentTarget;
    const status=this.shadowRoot.getElementById("protection-status");
    this._busy=true;
    try {
      const result=await this._hass.callService("cisco_catalyst","save_vlan_protection",{
        entry_id:this._entryId,
        protected_interfaces:form.elements.protected_interfaces.value.split(/[\n,]+/).map(x=>x.trim()).filter(Boolean).join(", "),
        protected_vlans:form.elements.protected_vlans.value.trim()
      },undefined,true,true);
      if(result?.response?.status!=="saved")throw Error("Save unverified");
      status.textContent="Protection settings saved.";
    }catch(e){status.textContent="Save failed: "+(e.message||e);}
    finally{this._busy=false;}
  }
  async previewStandaloneMove() {
    const source=Number(this.shadowRoot.getElementById("move-source").value);
    const destination=Number(this.shadowRoot.getElementById("move-destination").value);
    const el=this.shadowRoot.getElementById("move-ports");
    el.replaceChildren();
    if(!source||!destination||source===destination){
      el.textContent="Choose different source and destination VLANs.";return;
    }
    try{
      const response=await this._hass.callService("cisco_catalyst","preview_vlan_bulk_reassignment",
        {entry_id:this._entryId,source_vlan:source,destination_vlan:destination},undefined,false,true);
      const preview=response?.response;
      if(!Array.isArray(preview?.ports))throw Error("Preview unavailable");
      if(source!==Number(this.shadowRoot.getElementById("move-source").value)||
         destination!==Number(this.shadowRoot.getElementById("move-destination").value))return;
      const note=document.createElement("p");
      note.textContent="Read-only snapshot: "+preview.eligible_count+" eligible, "+
        preview.blocked_count+" blocked. "+(preview.request_blockers||[]).join(", ");
      el.append(note);
      for(const port of preview.ports.sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}))){
        const label=document.createElement("label");
        label.className="move-port";
        const checkbox=document.createElement("input");
        checkbox.type="checkbox";checkbox.value=port.name;
        checkbox.disabled=!port.eligible||Boolean(preview.request_blockers.length);
        label.append(checkbox,document.createTextNode(" "+shortInterfaceName(port.name)+
          (port.eligible?" — eligible":" — blocked: "+port.blockers.join(", "))));
        el.append(label);
      }
      this.updateMoveConfirmation();
    }catch(e){el.textContent="Preview unavailable: "+(e.message||e);}
  }
  updateMoveConfirmation() {
    const selected=this.shadowRoot.querySelectorAll('#move-ports input[type="checkbox"]:checked').length;
    const dest=Number(this.shadowRoot.getElementById("move-destination").value);
    const hint=this.shadowRoot.getElementById("move-confirm-hint");
    hint.textContent="Enter MOVE "+selected+" PORTS TO "+dest+" to confirm.";
  }
  async executeStandaloneMove(event) {
    event.preventDefault();
    if(this._busy)return;
    const source=Number(this.shadowRoot.getElementById("move-source").value);
    const destination=Number(this.shadowRoot.getElementById("move-destination").value);
    const ports=[...this.shadowRoot.querySelectorAll('#move-ports input[type="checkbox"]:checked')]
      .filter(input=>!input.disabled).map(input=>input.value);
    const confirmation=this.shadowRoot.getElementById("move-confirmation").value.trim();
    const status=this.shadowRoot.getElementById("move-status");
    if(!ports.length||confirmation!=="MOVE "+ports.length+" PORTS TO "+destination){
      status.textContent="Choose eligible ports and type the exact confirmation.";return;
    }
    this._busy=true;
    status.textContent="Rechecking and moving selected ports…";
    try {
      const response=await this._hass.callService("cisco_catalyst","reassign_vlan_access_ports",
        {entry_id:this._entryId,source_vlan:source,destination_vlan:destination,
         ports,confirmation},undefined,true,true);
      if(response?.response?.status!=="verified")throw Error("Move not verified");
      status.textContent="Verified moved ports: "+response.response.moved_ports.map(shortInterfaceName).join(", ")+
        (response.response.refresh_warning?" Note: "+response.response.refresh_warning+".":"");
      this.shadowRoot.getElementById("move-confirmation").value="";
      await this.refreshPortOverview();
      await this.previewStandaloneMove();
    }catch(e){status.textContent="Move not confirmed: "+(e.message||e)+
      ". Check switch state before retrying.";}
    finally{this._busy=false;}
  }
  updateStandaloneChoices() {
    for(const name of ["move-source","move-destination"]){
      const select=this.shadowRoot.getElementById(name);
      if(!select)continue;
      const previous=select.value;select.replaceChildren();
      for(const [id,label] of [...this._vlanNames].sort((a,b)=>a[0]-b[0])){
        if(id>1001||this._protectedVlans.has(id))continue;
        select.add(new Option(id+" — "+label,String(id)));
      }
      if([...select.options].some(x=>x.value===previous))select.value=previous;
    }
  }
  async previewDelete() {
    const vlan_id=Number(this.shadowRoot.getElementById("delete-vlan").value);
    const el=this.shadowRoot.getElementById("delete-preview");
    if(!vlan_id)return;
    try{
      const response=await this._hass.callService("cisco_catalyst","preview_vlan_delete",
        {entry_id:this._entryId,vlan_id},undefined,false,true);
      const ports=response?.response?.access_ports;
      if(!Array.isArray(ports))throw Error("Preview unavailable");
      const blocked=response?.response?.protected_or_unverified_ports||[];
      const snapshot=response?.response?.snapshot_only?"Last polling snapshot, not a fresh switch read. ":"";
      if(this.shadowRoot.getElementById("delete-section").hidden||Number(this.shadowRoot.getElementById("delete-vlan").value)!==vlan_id)return;
      el.textContent=snapshot+(ports.length?"Access ports ("+ports.length+"): "+ports.join(", "):
        "No detected access ports assigned to this VLAN.")+
        (blocked.length?" Protected or unverified ports: "+blocked.join(", "):"");
      this.updateDeleteMode(ports.length);
      if(ports.length)await this.previewBulkMove();
    }catch(e){if(!this.shadowRoot.getElementById("delete-section").hidden&&Number(this.shadowRoot.getElementById("delete-vlan").value)===vlan_id){el.textContent="Port impact check unavailable: "+(e.message||e);this.updateDeleteMode(null);}}
  }
  async previewBulkMove() {
    const el=this.shadowRoot.getElementById("bulk-move-preview");
    const form=this.shadowRoot.getElementById("delete");
    if(!el||!form)return;
    if(this._deletePortCount===null||this._deletePortCount===0){el.textContent="";return;}
    const source_vlan=Number(form.elements.vlan.value);
    const destination_vlan=Number(form.elements.destination.value);
    if(!source_vlan||!destination_vlan){
      el.textContent="Select a destination VLAN to preview port eligibility.";
      return;
    }
    el.textContent="Checking cached port eligibility…";
    try {
      const response=await this._hass.callService("cisco_catalyst","preview_vlan_bulk_reassignment",
        {entry_id:this._entryId,source_vlan,destination_vlan},undefined,false,true);
      const result=response?.response;
      if(!Array.isArray(result?.ports)||!Array.isArray(result?.request_blockers))
        throw Error("Preview unavailable");
      if(this.shadowRoot.getElementById("delete-section").hidden||this._deletePortCount===null||this._deletePortCount===0||Number(form.elements.vlan.value)!==source_vlan||
        Number(form.elements.destination.value)!==destination_vlan)return;
      const request=result.request_blockers.length?" Request blockers: "+result.request_blockers.join(", ")+".":"";
      const ports=result.ports.length?" Ports: "+result.ports.map(p=>p.name+" — "+
        (p.eligible?"eligible":"blocked ("+p.blockers.join(", ")+")")).join("; ")+".":" No source access ports detected.";
      el.textContent="Last polling snapshot only (read-only). "+result.eligible_count+
        " eligible, "+result.blocked_count+" blocked."+request+ports+
        " Actual execution requires fresh verification.";
    } catch(e) {
      if(!this.shadowRoot.getElementById("delete-section").hidden&&Number(form.elements.vlan.value)===source_vlan)
        el.textContent="Read-only reassignment preview unavailable: "+(e.message||e);
    }
  }
  async deleteVlan(event) {
    event.preventDefault();
    if(this._busy)return;
    const form=event.currentTarget;
    const vlan_id=Number(form.elements.vlan.value);
    const confirmation=form.elements.confirmation.value.trim();
    if(!isDeletableVlanId(vlan_id)){this.shadowRoot.getElementById("delete-status").textContent="Invalid VLAN deletion choice.";return;}
    const needsMove=this._deletePortCount!==null&&this._deletePortCount>0;
    const destination_vlan=Number(form.elements.destination.value);
    const status=this.shadowRoot.getElementById("delete-status");
    if(confirmation!=="DELETE "+vlan_id){status.textContent="Enter DELETE "+vlan_id+" to confirm.";return;}
    if(this._deletePortCount===null){status.textContent="Port membership preview unavailable; refresh before deleting.";return;}
    if(needsMove && (!destination_vlan || destination_vlan===vlan_id)){
      status.textContent="Select a different existing destination VLAN.";return;
    }
    this._busy=true;const button=form.querySelector("button");button.disabled=true;
    status.textContent="Checking and deleting VLAN…";
    try {
      const payload={entry_id:this._entryId,vlan_id,confirmation};
      if(needsMove)payload.destination_vlan=destination_vlan;
      const result=await this._hass.callService("cisco_catalyst","delete_vlan",payload,undefined,true,true);
      if(result?.response?.status!=="verified")throw Error("Deletion not verified");
      const notice="VLAN "+vlan_id+" deleted and verified."+
        (result.response.refresh_warning?" "+result.response.refresh_warning:"");
      // Return to the unselected inventory view. Clearing first also makes
      // pending asynchronous previews ignore this obsolete VLAN.
      this.shadowRoot.getElementById("delete-section").hidden=true;
      form.reset();
      form.elements.vlan.selectedIndex=-1;
      form.elements.confirmation.value="";
      this.shadowRoot.getElementById("delete-target").textContent="";
      this.shadowRoot.getElementById("delete-preview").textContent="";
      this.shadowRoot.getElementById("bulk-move-preview").textContent="";
      status.textContent="";
      this.updateDeleteMode(null);
      await this.loadInventoryNames();
      this.shadowRoot.getElementById("inventory-status").textContent=notice;
    }catch(e){status.textContent="Deletion not confirmed: "+(e.message||e)+". Inspect VLAN and port states before retrying.";}
    finally{this._busy=false;this.updateDeleteMode(this._deletePortCount);}
  }
  async rename(event) {
    event.preventDefault();
    if(this._busy)return;
    const form=event.currentTarget;
    const vlan_id=Number(form.elements.vlan.value),name=form.elements.name.value.trim();
    const status=this.shadowRoot.getElementById("rename-status");
    if(!Number.isInteger(vlan_id)||vlan_id<2||vlan_id>1001||!/^[A-Za-z0-9_-]{1,32}$/.test(name)){
      status.textContent="Invalid VLAN ID or name.";return;
    }
    if(!this._vlanNames.has(vlan_id)){status.textContent="Select an existing VLAN.";return;}
    this._busy=true;
    const controls=[form.elements.name,form.querySelector('button[type="submit"]')];
    for(const control of controls)control.disabled=true;
    status.textContent="Renaming VLAN…";
    try{
      const result=await this._hass.callService("cisco_catalyst","rename_vlan",
        {entry_id:this._entryId,vlan_id,name},undefined,true,true);
      if(result?.response?.status!=="verified")throw Error("No verified response returned");
      status.textContent="VLAN "+vlan_id+" renamed to "+name+" and verified.";
      await this.loadInventoryNames();
      form.elements.name.value=this._vlanNames.get(vlan_id)||name;
    }catch(e){status.textContent="Rename not confirmed: "+(e.message||e)+". Refresh inventory before retrying.";}
    finally{this._busy=false;for(const control of controls)control.disabled=false;}
  }
  async create(event) {
    event.preventDefault();
    if(this._busy)return;
    const form=event.currentTarget;
    const vlan_id=Number(form.elements.vlan.value),name=form.elements.name.value.trim();
    const status=this.shadowRoot.getElementById("status");
    if(!Number.isInteger(vlan_id)||vlan_id<2||vlan_id>1001||!/^[A-Za-z0-9_-]{1,32}$/.test(name)){status.textContent="Invalid VLAN ID or name.";return;}
    this._busy=true;
    const controls=[form.elements.vlan,form.elements.name,form.querySelector('button[type="submit"]')];
    for(const control of controls)control.disabled=true;
    status.textContent="Creating VLAN…";
    try {
      const result=await this._hass.callService("cisco_catalyst","create_vlan",{entry_id:this._entryId,vlan_id,name},undefined,true,true);
      if(result?.response?.status!=="verified")throw Error("No verified result returned");
      status.textContent="VLAN "+vlan_id+" ("+name+") created and verified.";
      form.reset();
      await this.loadInventoryNames();
      this.updateInventory();
    } catch(e){status.textContent="Creation not confirmed: "+(e.message||e)+". Check VLAN inventory before retrying.";}
    finally{
      this._busy=false;
      for(const control of controls)control.disabled=false;
    }
  }
}
if(!customElements.get("cisco-catalyst-vlan-panel"))customElements.define("cisco-catalyst-vlan-panel",CiscoCatalystVlanPanel);
