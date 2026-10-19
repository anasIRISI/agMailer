import {useCallback,useEffect,useState,useRef} from 'react'
import {api} from '../services/api'
export function useApi<T>(path:string,poll=0){
  const [data,setData]=useState<T>();const [error,setError]=useState('');const [loading,setLoading]=useState(true)
  const sequence=useRef(0)
  const refresh=useCallback(async()=>{const id=++sequence.current;try{const result=await api<T>(path);if(id===sequence.current){setData(result);setError('')}}catch(e){if(id===sequence.current)setError((e as Error).message)}finally{if(id===sequence.current)setLoading(false)}},[path])
  useEffect(()=>{void refresh();if(poll){const id=setInterval(()=>void refresh(),poll);return()=>clearInterval(id)}},[refresh,poll])
  return {data,error,loading,refresh}
}
