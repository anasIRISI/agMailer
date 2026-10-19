export async function api<T>(path:string, options:RequestInit={}):Promise<T> {
  const headers:Record<string,string> = {'X-PFE-Client':'local-app'}
  if(options.body && !(options.body instanceof FormData)) headers['Content-Type']='application/json'
  let response:Response
  try{response=await fetch('/api'+path,{...options,headers:{...headers,...options.headers}})}catch{throw new Error('Impossible de joindre le serveur local. Vérifiez que PFE Mail Agent est démarré.')}
  if(!response.ok){let message='Le serveur local est indisponible.';try{const data=await response.json();message=typeof data.detail==='string'?data.detail: data.detail?.map((x:{msg:string})=>x.msg).join(' · ')||message}catch{/* response may not be JSON */}throw new Error(message)}
  return response.json()
}
export const json = (method:string,body:unknown):RequestInit=>({method,body:JSON.stringify(body)})
export function date(value:string|null){return value?new Date(value+'Z').toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'short',timeZone:'Africa/Casablanca'}):'—'}
