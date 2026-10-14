import {useEffect, useRef, useState} from 'react';
import GlassFolder, {hashString, type ArtRecipe, type FolderFile} from './glass-folder';
import {exportLink} from '../../lib/briefings';

const artwork: ArtRecipe = {style:'marble', colors:['#111425','#2a2850','#837bbb','#c6d4f2','#4e6193','#171a30'], scale:.8, warp:2.8, gloss:.5, veins:.22};

/** The supplied Glass Folder, containing actual exports only. */
export function ReportFolder({id,label='Report & workbook',meta='PDF · Excel · evidence',onOpen}:{id:string;label?:string;meta?:string;onOpen?:()=>void}) {
  const container=useRef<HTMLDivElement>(null);
  const [width,setWidth]=useState(280);
  useEffect(()=>{
    const el=container.current;if(!el)return;
    const observer=new ResizeObserver(entries=>setWidth(Math.max(160,Math.min(310,entries[0].contentRect.width))));
    observer.observe(el);return()=>observer.disconnect();
  },[]);
  const files:FolderFile[]=[
    {name:'Client report',meta:'PDF',href:exportLink(id,'pdf'),art:artwork},
    {name:'Analysis workbook',meta:'XLSX',href:exportLink(id,'xlsx')},
    {name:'Evidence register',meta:'CSV',href:exportLink(id,'csv')},
  ];
  return <div className="studio-folder" ref={container}><GlassFolder key={id} label={label} meta={meta} art={artwork} seed={hashString(id)} tone="dark" files={files} fileList action="none" width={width} appear={false}/>{onOpen&&<button className="studio-folder-open" onClick={onOpen}>Open analysis <span aria-hidden="true">↗</span></button>}</div>;
}
