export interface Recipient {id:number;email:string;entreprise:string;nom_recruteur:string;poste:string;excluded:boolean;contacted:boolean;letter_document_id:number|null}
export interface Document {id:number;name:string;kind:string;size:number;created_at:string}
export interface Template {id:number;name:string;subject:string;body:string;signature:string;is_html:boolean}
export interface Campaign extends Template {status:string;simulation:boolean;total:number;counts:Record<string,number>;error:string;document_ids:number[];daily_limit:number;delay_seconds:number;campaign_limit:number;created_at:string}
export interface Delivery {id:number;campaign_id:number;campaign_name:string;email:string;entreprise:string;poste:string;subject:string;body:string;is_html:boolean;status:string;gmail_id:string;sent_at:string|null;attempted_at:string|null;error:string;document_ids:number[];replied:boolean;sender:string;message_id:string}
export interface GmailStatus {connected:boolean;email:string;configured:boolean;connecting:boolean;error:string}
export interface DashboardData {recipients:number;campaigns:number;counts:Record<string,number>;sent_today:number;daily_used:number;daily_limit:number;chart:{date:string;count:number}[];recent:Delivery[]}
